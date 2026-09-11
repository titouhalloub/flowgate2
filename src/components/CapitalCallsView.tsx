import React, { useState } from 'react';
import { CapitalCallNotice } from '../types';
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
}

export const CapitalCallsView: React.FC<CapitalCallsViewProps> = ({
  capitalCalls,
  onReviewCall,
  onCreateCall,
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
                return (
                  <tr key={call.id} className="hover:bg-gray-50/60 transition-colors">
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
                        <span className="text-xs text-gray-400 font-medium">Settled</span>
                      )}
                    </td>
                  </tr>
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
