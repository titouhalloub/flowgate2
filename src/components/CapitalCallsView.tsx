import React, { useState, useEffect } from 'react';
import { CapitalCallNotice, CapitalCallPayment } from '../types';
import * as liveApi from '../services/api';
import {
  DollarSign,
  Calendar,
  AlertCircle,
  CheckCircle2,
  Filter,
  PlusCircle,
  FileSpreadsheet,
  Building2,
  Clock,
  ArrowUpRight,
} from 'lucide-react';

interface CapitalCallsViewProps {
  capitalCalls: CapitalCallNotice[];
  onReviewCall: (callId: string, status: 'approved' | 'rejected', reviewer: string) => void;
  onCreateCall: (call: Omit<CapitalCallNotice, 'id' | 'status' | 'created_at' | 'reconciled'>) => void;
  onRefreshCalls?: () => Promise<void> | void;
}

export const CapitalCallsView: React.FC<CapitalCallsViewProps> = ({
  capitalCalls,
  onReviewCall,
  onCreateCall,
  onRefreshCalls,
}) => {
  const [filterOverdue, setFilterOverdue] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [reviewerName, setReviewerName] = useState('Danial Vance (Fund Controller)');

  // Form State
  const [funderName, setFunderName] = useState('');
  const [capitalOwing, setCapitalOwing] = useState<number>(250000);
  const [currency, setCurrency] = useState('USD');
  const [dueDate, setDueDate] = useState('2026-04-15');
  const [wireDetails, setWireDetails] = useState('ABA 121000358 / Acct 984-2194819-01 (Silicon Valley Bank)');

  // Phase C: per-call payments panel state. Payments are the server's truth
  // when live; demo mode keeps a local map so the panel still works.
  const [expandedCallId, setExpandedCallId] = useState<string | null>(null);
  const [livePayments, setLivePayments] = useState<Record<string, CapitalCallPayment[]>>({});
  const [demoPayments, setDemoPayments] = useState<Record<string, CapitalCallPayment[]>>({});
  const [payAmount, setPayAmount] = useState<string>('');
  const [payReference, setPayReference] = useState<string>('');
  const [payBusy, setPayBusy] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  useEffect(() => {
    if (expandedCallId === null || !liveApi.isLive()) return;
    let cancelled = false;
    setPayError(null);
    liveApi
      .listCapitalCallPayments(expandedCallId)
      .then((rows) => {
        if (!cancelled) {
          setLivePayments((prev) => ({ ...prev, [expandedCallId]: rows }));
        }
      })
      .catch(() => {
        if (!cancelled) setPayError('Could not load payments from the backend.');
      });
    return () => {
      cancelled = true;
    };
  }, [expandedCallId]);

  const paymentsFor = (call: CapitalCallNotice): CapitalCallPayment[] => {
    const map = liveApi.isLive() ? livePayments : demoPayments;
    return map[call.id] || [];
  };

  const remainingFor = (call: CapitalCallNotice): number => {
    const paid = paymentsFor(call).reduce((acc, p) => acc + p.amount, 0);
    return Math.max(0, call.capital_owing - paid);
  };

  const statusFor = (call: CapitalCallNotice): string => {
    if (liveApi.isLive() && call.payment_status) return call.payment_status;
    const remaining = remainingFor(call);
    if (remaining <= 0.005) return 'paid';
    if (remaining < call.capital_owing - 0.005) return 'partial';
    return 'unpaid';
  };

  const handleRecordPayment = async (call: CapitalCallNotice) => {
    const amount = parseFloat(payAmount);
    setPayError(null);
    if (!amount || amount <= 0) {
      setPayError('Enter a positive payment amount.');
      return;
    }
    if (amount > remainingFor(call) + 0.005) {
      setPayError('Payment exceeds the remaining balance — overpayments are rejected, never absorbed.');
      return;
    }
    setPayBusy(true);
    try {
      if (liveApi.isLive()) {
        await liveApi.recordCapitalCallPayment(call.id, {
          amount,
          currency: call.currency,
          reference: payReference.trim() || undefined,
          recorded_by: reviewerName.trim() || 'unnamed reviewer',
        });
        const rows = await liveApi.listCapitalCallPayments(call.id);
        setLivePayments((prev) => ({ ...prev, [call.id]: rows }));
        if (onRefreshCalls) await onRefreshCalls();
      } else {
        const payment: CapitalCallPayment = {
          id: 'pay_' + Math.random().toString(36).substring(2, 9),
          capital_call_id: call.id,
          amount,
          currency: call.currency,
          paid_date: new Date().toISOString(),
          reference: payReference.trim() || null,
          recorded_by: reviewerName.trim() || 'unnamed reviewer',
          created_at: new Date().toISOString(),
        };
        setDemoPayments((prev) => ({
          ...prev,
          [call.id]: [...(prev[call.id] || []), payment],
        }));
      }
      setPayAmount('');
      setPayReference('');
    } catch (e: unknown) {
      setPayError(e instanceof Error ? e.message : 'Could not record the payment.');
    } finally {
      setPayBusy(false);
    }
  };

  const isOverdue = (call: CapitalCallNotice) => {
    if (!call.due_date || call.status === 'approved') return false;
    return new Date(call.due_date) < new Date();
  };

  const displayedCalls = filterOverdue
    ? capitalCalls.filter(isOverdue)
    : capitalCalls;

  const totalOwing = capitalCalls.reduce((acc, c) => acc + c.capital_owing, 0);
  const totalApproved = capitalCalls
    .filter((c) => c.status === 'approved')
    .reduce((acc, c) => acc + c.capital_owing, 0);
  const overdueCount = capitalCalls.filter(isOverdue).length;

  const handleSubmitCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!funderName.trim()) return;

    onCreateCall({
      funder_name: funderName,
      currency,
      capital_owing: capitalOwing,
      due_date: dueDate ? dueDate + 'T00:00:00Z' : null,
      wire_details: wireDetails,
      source_text: 'Manual entry via Flowgate Operational Dashboard',
    });

    setFunderName('');
    setShowCreateModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner Metric Cards */}
      <div className="bg-[#E8EFFD] rounded-2xl p-4 sm:p-5">
        <div className="text-[11px] font-bold tracking-wider text-[#5C4DE5] uppercase mb-3">
          CAPITAL CALL DRAWDOWNS & SETTLEMENT
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#7048E8] text-white flex items-center justify-center">
                <DollarSign className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Total Capital Called</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              ${totalOwing.toLocaleString()} <span className="text-xs font-normal text-gray-400">USD</span>
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              {capitalCalls.length} drawdown notices issued
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#20C997] text-white flex items-center justify-center">
                <CheckCircle2 className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Cleared & Settled</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight text-emerald-600">
              ${totalApproved.toLocaleString()} <span className="text-xs font-normal text-gray-400">USD</span>
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              {capitalCalls.filter((c) => c.status === 'approved').length} confirmed receipts
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FF6B2C] text-white flex items-center justify-center">
                <Clock className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Overdue Notices</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              {overdueCount} <span className="text-xs font-normal text-gray-400">notices</span>
            </div>
            <div className="text-[11px] text-amber-600 mt-1 font-medium">
              Requires LP wire follow-up
            </div>
          </div>
        </div>
      </div>

      {/* Main Table Panel */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-3">
          <div className="flex items-center gap-3">
            <div>
              <h3 className="text-sm font-bold text-gray-900">
                Capital Call Ingestion & Review Gate
              </h3>
              <p className="text-xs text-gray-500">
                Drawdown notices extracted from subscription agreements and LP notices
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setFilterOverdue(!filterOverdue)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-colors cursor-pointer ${
                filterOverdue
                  ? 'bg-amber-50 border-amber-300 text-amber-800'
                  : 'bg-[#F4F6FC] border-gray-200 text-gray-600 hover:bg-gray-100'
              }`}
            >
              <Filter className="w-3.5 h-3.5" />
              <span>{filterOverdue ? 'Showing Overdue Only' : 'Filter Overdue'}</span>
            </button>

            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-[#7048E8] hover:bg-[#5C38D1] text-white text-xs font-bold transition-colors cursor-pointer shadow-xs"
            >
              <PlusCircle className="w-4 h-4" />
              <span>Create Call Notice</span>
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-50/80 text-gray-500 font-semibold border-b border-gray-100">
              <tr>
                <th className="px-3 py-2.5">LP / Institutional Funder</th>
                <th className="px-3 py-2.5">Amount Due</th>
                <th className="px-3 py-2.5">Due Date</th>
                <th className="px-3 py-2.5">Wire Instructions</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right">Human Review Gate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-gray-800">
              {displayedCalls.map((call) => {
                const overdue = isOverdue(call);
                const payStatus = call.status === 'approved' ? statusFor(call) : null;
                const remaining = remainingFor(call);
                const expanded = expandedCallId === call.id;
                return (
                <React.Fragment key={call.id}>
                  <tr className="hover:bg-gray-50/60 transition-colors">
                    <td className="px-3 py-3 font-semibold text-gray-900 flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-full bg-[#7048E8]" />
                      <span>{call.funder_name}</span>
                    </td>
                    <td className="px-3 py-3 font-mono font-bold text-[#7048E8]">
                      ${call.capital_owing.toLocaleString()} {call.currency}
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap">
                      {call.due_date ? (
                        <div className="flex items-center gap-1.5">
                          <span className={overdue ? 'text-red-600 font-bold' : 'text-gray-600'}>
                            {new Date(call.due_date).toLocaleDateString()}
                          </span>
                          {overdue && (
                            <span className="px-1.5 py-0.5 rounded-full bg-red-100 text-red-700 text-[10px] font-bold">
                              Overdue
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-[11px] text-gray-500 max-w-xs truncate">
                      {call.wire_details || 'Standard wire instructions on file'}
                    </td>
                    <td className="px-3 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] uppercase font-bold ${
                          call.status === 'approved'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : call.status === 'rejected'
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        {call.status.replace(/_/g, ' ')}
                      </span>
                      {call.reviewer && (
                        <div className="text-[10px] text-gray-400 mt-0.5">by {call.reviewer}</div>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right">
                      {call.status === 'pending_approval' ? (
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            onClick={() => onReviewCall(call.id, 'rejected', reviewerName)}
                            className="px-2.5 py-1 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 text-xs font-bold transition-colors cursor-pointer"
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => onReviewCall(call.id, 'approved', reviewerName)}
                            className="px-3 py-1 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white text-xs font-bold transition-colors cursor-pointer shadow-2xs"
                          >
                            Approve
                          </button>
                        </div>
                      ) : (
                        <div className="inline-flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] uppercase font-bold border ${
                              payStatus === 'paid'
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : payStatus === 'partial'
                                ? 'bg-amber-50 text-amber-700 border-amber-200'
                                : 'bg-gray-50 text-gray-500 border-gray-200'
                            }`}
                          >
                            {payStatus}
                          </span>
                          {payStatus !== 'paid' && (
                            <span className="text-[10px] text-gray-400 font-medium">
                              {remaining.toLocaleString()} {call.currency} left
                            </span>
                          )}
                          <button
                            onClick={() => setExpandedCallId(expanded ? null : call.id)}
                            className="px-2.5 py-1 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 text-xs font-bold transition-colors cursor-pointer"
                          >
                            {expanded ? 'Hide' : 'Payments'}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                  {expanded && call.status === 'approved' && (
                    <tr className="bg-[#F4F6FB]/60">
                      <td colSpan={6} className="px-3 py-4">
                        <div className="space-y-3">
                          {/* Payment history */}
                          <div className="space-y-1.5">
                            {paymentsFor(call).length === 0 ? (
                              <div className="text-[11px] text-gray-400 font-medium">
                                No payments recorded yet — remaining balance{' '}
                                {remaining.toLocaleString()} {call.currency}.
                              </div>
                            ) : (
                              paymentsFor(call).map((p) => (
                                <div
                                  key={p.id}
                                  className="flex items-center justify-between bg-white rounded-lg px-3 py-2 border border-gray-100 text-[11px]"
                                >
                                  <span className="font-mono font-bold text-emerald-700">
                                    +{p.amount.toLocaleString()} {p.currency}
                                  </span>
                                  <span className="text-gray-500">
                                    {p.paid_date ? new Date(p.paid_date).toLocaleDateString() : '—'}
                                    {p.reference ? ` · ref ${p.reference}` : ''}
                                  </span>
                                  <span className="text-gray-400">by {p.recorded_by}</span>
                                </div>
                              ))
                            )}
                          </div>

                          {/* Record payment form */}
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              placeholder={`Amount (${call.currency})`}
                              value={payAmount}
                              onChange={(e) => setPayAmount(e.target.value)}
                              className="w-32 bg-white border border-gray-200 rounded-lg px-2 py-1.5 text-gray-800 font-mono focus:border-[#7048E8] outline-none"
                            />
                            <input
                              type="text"
                              placeholder="Wire reference (optional)"
                              value={payReference}
                              onChange={(e) => setPayReference(e.target.value)}
                              className="flex-1 min-w-[160px] bg-white border border-gray-200 rounded-lg px-2 py-1.5 text-gray-800 focus:border-[#7048E8] outline-none"
                            />
                            <button
                              onClick={() => handleRecordPayment(call)}
                              disabled={payBusy}
                              className="px-3 py-1.5 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] disabled:opacity-50 text-white text-xs font-bold transition-colors cursor-pointer shadow-2xs"
                            >
                              {payBusy ? 'Recording…' : 'Record Payment'}
                            </button>
                          </div>
                          {payError && (
                            <div className="text-[11px] text-red-600 font-semibold flex items-center gap-1.5">
                              <AlertCircle className="w-3.5 h-3.5" />
                              {payError}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: Create Call Notice */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-gray-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-gray-100 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl text-xs">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <h3 className="text-base font-bold text-gray-900">
                Issue Capital Call Notice
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-gray-400 hover:text-gray-600 cursor-pointer text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmitCreate} className="space-y-3">
              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                  LP PARTNER / INSTITUTIONAL FUNDER
                </label>
                <input
                  type="text"
                  value={funderName}
                  onChange={(e) => setFunderName(e.target.value)}
                  placeholder="e.g. Sovereign Wealth Asset Management"
                  className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-500 font-semibold text-[11px] mb-1">CAPITAL OWING</label>
                  <input
                    type="number"
                    value={capitalOwing}
                    onChange={(e) => setCapitalOwing(parseInt(e.target.value, 10) || 0)}
                    className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                  />
                </div>
                <div>
                  <label className="block text-gray-500 font-semibold text-[11px] mb-1">CURRENCY</label>
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                  >
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                    <option value="AED">AED (د.إ)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">PAYMENT DUE DATE</label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                />
              </div>

              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">WIRE TRANSFER INSTRUCTIONS</label>
                <input
                  type="text"
                  value={wireDetails}
                  onChange={(e) => setWireDetails(e.target.value)}
                  className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-[#F4F6FC] hover:bg-gray-200 text-gray-700 text-xs font-semibold cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white font-bold text-xs shadow-xs cursor-pointer"
                >
                  Issue Call Notice
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
