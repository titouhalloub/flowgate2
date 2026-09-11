import React, { useState } from 'react';
import {
  CapTableSnapshot,
  CapTableEvent,
  CapTableProposal,
  Investor,
  CapTableEventType,
} from '../types';
import {
  PlusCircle,
  Clock,
  Shield,
  Layers,
  AlertCircle,
  Building2,
  Users,
  CheckCircle2,
  XCircle,
} from 'lucide-react';

interface CapTableViewProps {
  snapshot: CapTableSnapshot;
  events: CapTableEvent[];
  proposals: CapTableProposal[];
  investors: Investor[];
  onRecordEvent: (event: Omit<CapTableEvent, 'id' | 'timestamp'>) => void;
  onApproveProposal: (proposalId: string, reviewer: string) => void;
  onRejectProposal: (proposalId: string, reviewer: string) => void;
  onLinkInvestor: (proposalId: string, investorId: string) => void;
}

export const CapTableView: React.FC<CapTableViewProps> = ({
  snapshot,
  events,
  proposals,
  investors,
  onRecordEvent,
  onApproveProposal,
  onRejectProposal,
  onLinkInvestor,
}) => {
  const [showEventModal, setShowEventModal] = useState(false);
  const [reviewerName, setReviewerName] = useState('Sarah Jenkins (Legal VP)');

  // New Event Form State
  const [eventType, setEventType] = useState<CapTableEventType>('issuance');
  const [holderName, setHolderName] = useState('');
  const [shareCount, setShareCount] = useState(50000);
  const [shareClass, setShareClass] = useState('Common');
  const [sharePrice, setSharePrice] = useState(10.0);
  const [toHolderName, setToHolderName] = useState('');
  const [formError, setFormError] = useState('');

  const colors = [
    'bg-[#FAB005]',
    'bg-[#20C997]',
    'bg-[#FF6B2C]',
    'bg-[#7048E8]',
    'bg-[#5C4DE5]',
    'bg-[#339AF0]',
  ];

  const handleCreateEvent = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');

    if (!holderName.trim()) {
      setFormError('Holder name is required.');
      return;
    }

    if (shareCount <= 0) {
      setFormError('Share count must be greater than zero.');
      return;
    }

    // Overdraft check for transfer or cancellation
    if (eventType === 'transfer' || eventType === 'cancellation') {
      const existing = snapshot.positions.find(
        (p) => p.holder_name.toLowerCase() === holderName.toLowerCase()
      );
      if (!existing || existing.shares < shareCount) {
        setFormError(
          `Overdraft prevented: Holder "${holderName}" only holds ${existing ? existing.shares.toLocaleString() : 0} shares.`
        );
        return;
      }
    }

    onRecordEvent({
      issuer_name: snapshot.issuer_name,
      event_type: eventType,
      holder_id: 'inv_' + holderName.toLowerCase().replace(/[^a-z0-9]/g, '_'),
      holder_name: holderName,
      share_count: shareCount,
      share_class: shareClass,
      share_price: sharePrice,
      to_holder_id: toHolderName ? 'inv_' + toHolderName.toLowerCase().replace(/[^a-z0-9]/g, '_') : undefined,
      to_holder_name: toHolderName || undefined,
    });

    setHolderName('');
    setToHolderName('');
    setShowEventModal(false);
  };

  const pendingProposals = proposals.filter((p) => p.status === 'proposed');

  return (
    <div className="space-y-6">
      {/* Top Overview Banner matching Dashboard Style */}
      <div className="bg-[#E8EFFD] rounded-2xl p-4 sm:p-5">
        <div className="text-[11px] font-bold tracking-wider text-[#5C4DE5] uppercase mb-3">
          CAP TABLE METRICS & CAPITALIZATION
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#7048E8] text-white flex items-center justify-center">
                <Building2 className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Issuer Entity</span>
            </div>
            <div className="text-xl font-extrabold text-[#111827] mt-3 tracking-tight truncate">
              {snapshot.issuer_name}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              San Jose Shark / Series A
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FAB005] text-white flex items-center justify-center">
                <Users className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Fully Diluted Shares</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              {snapshot.total_fully_diluted_shares.toLocaleString()}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              {snapshot.positions.length} active position holders
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#20C997] text-white flex items-center justify-center">
                <Shield className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">State Model</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              Event-Sourced
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              Overdrafts blocked at write time
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FF6B2C] text-white flex items-center justify-center">
                <Clock className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Pending Review</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              {pendingProposals.length} Proposals
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              Requires legal VP approval
            </div>
          </div>
        </div>
      </div>

      {/* Visual Ownership Segmented Bar Card */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-3">
          <div>
            <h3 className="text-sm sm:text-base font-bold text-gray-900">Current Equity Distribution</h3>
            <p className="text-xs text-gray-500">
              Computed directly by replaying immutable events — never stored as a mutable static number.
            </p>
          </div>

          <button
            onClick={() => setShowEventModal(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#7048E8] text-white text-xs font-bold hover:bg-[#5C38D1] transition-colors cursor-pointer shadow-xs"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Record Event</span>
          </button>
        </div>

        {/* Ownership Bar */}
        <div className="w-full h-8 rounded-xl bg-gray-100 overflow-hidden flex border border-gray-200/80">
          {snapshot.positions.map((pos, idx) => (
            <div
              key={pos.holder_id}
              style={{ width: `${pos.ownership_percent}%` }}
              title={`${pos.holder_name}: ${pos.ownership_percent}% (${pos.shares.toLocaleString()} shares)`}
              className={`h-full flex items-center justify-center text-[11px] font-bold text-white px-1 truncate transition-all ${
                colors[idx % colors.length]
              }`}
            >
              {pos.ownership_percent >= 8 ? `${pos.ownership_percent}%` : ''}
            </div>
          ))}
        </div>

        {/* Ownership Legend */}
        <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
          {snapshot.positions.map((pos, idx) => (
            <div key={pos.holder_id} className="flex items-center gap-1.5">
              <span className={`w-2.5 h-2.5 rounded-sm ${colors[idx % colors.length]}`} />
              <span className="font-semibold text-gray-800">{pos.holder_name}</span>
              <span className="text-gray-400">&mdash;</span>
              <span className="font-bold text-[#7048E8]">{pos.ownership_percent}%</span>
              <span className="text-gray-500">({pos.shares.toLocaleString()} sh)</span>
            </div>
          ))}
        </div>
      </div>

      {/* Grid: Stakeholder Positions & Cap Table Proposals */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Positions Table (7 cols) */}
        <div className="lg:col-span-7 bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
          <div className="flex items-center justify-between border-b border-gray-100 pb-3">
            <div>
              <h3 className="text-sm font-bold text-gray-900">Stakeholder Registry</h3>
              <p className="text-xs text-gray-500">Active equity and option holders</p>
            </div>
            <span className="text-xs font-bold text-[#7048E8] bg-[#EBE7FD] px-2.5 py-1 rounded-full">
              {snapshot.positions.length} Holders
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-gray-50/80 text-gray-500 font-semibold border-b border-gray-100">
                <tr>
                  <th className="px-3 py-2.5">Stakeholder</th>
                  <th className="px-3 py-2.5">Class</th>
                  <th className="px-3 py-2.5 text-right">Shares</th>
                  <th className="px-3 py-2.5 text-right">Ownership</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 text-gray-800">
                {snapshot.positions.map((p, idx) => (
                  <tr key={p.holder_id} className="hover:bg-gray-50/60 transition-colors">
                    <td className="px-3 py-3 font-medium flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${colors[idx % colors.length]}`} />
                      <span className="font-bold text-gray-900">{p.holder_name}</span>
                    </td>
                    <td className="px-3 py-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-[#F4F6FC] border border-gray-200 text-gray-600">
                        {p.share_class}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right font-mono font-semibold">
                      {p.shares.toLocaleString()}
                    </td>
                    <td className="px-3 py-3 text-right font-mono font-bold text-[#7048E8]">
                      {p.ownership_percent.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Cap Table Proposals & Human Review Gate (5 cols) */}
        <div className="lg:col-span-5 bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
          <div className="flex items-center justify-between border-b border-gray-100 pb-3">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#EBE7FD] text-[#7048E8] flex items-center justify-center">
                <Shield className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-gray-900">Human Approval Gate</h3>
                <p className="text-[11px] text-gray-500">Legal verification for proposals</p>
              </div>
            </div>
            <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-[#EBE7FD] text-[#7048E8]">
              {pendingProposals.length} Pending
            </span>
          </div>

          <div className="p-3 bg-[#F8FAFD] rounded-xl border border-gray-200/80 text-xs space-y-1">
            <label className="text-gray-500 font-semibold block text-[11px]">REVIEWER SIGNATURE</label>
            <input
              type="text"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              className="w-full bg-white border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs text-gray-900 font-semibold focus:border-[#7048E8] outline-none"
            />
          </div>

          {proposals.length === 0 ? (
            <div className="p-6 text-center border border-dashed border-gray-200 rounded-xl bg-gray-50/50">
              <Clock className="w-6 h-6 text-gray-400 mx-auto mb-2" />
              <div className="text-xs font-semibold text-gray-600">No proposals pending review</div>
              <div className="text-[11px] text-gray-400 mt-1">
                Process a Subscription Agreement in the Intake Pipeline to seed proposals.
              </div>
            </div>
          ) : (
            <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
              {proposals.map((prop) => (
                <div
                  key={prop.id}
                  className={`p-3.5 rounded-xl border text-xs transition-all ${
                    prop.status === 'proposed'
                      ? 'bg-white border-purple-200 shadow-xs'
                      : prop.status === 'approved'
                      ? 'bg-emerald-50/40 border-emerald-200'
                      : 'bg-red-50/40 border-red-200'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-gray-900 truncate">{prop.holder_name}</span>
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                        prop.status === 'proposed'
                          ? 'bg-[#EBE7FD] text-[#7048E8]'
                          : prop.status === 'approved'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {prop.status}
                    </span>
                  </div>

                  <div className="text-[11px] text-gray-600 space-y-1">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Shares Requested:</span>
                      <span className="font-semibold text-gray-800 font-mono">
                        {prop.share_count.toLocaleString()} ({prop.share_class})
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Unit Price:</span>
                      <span className="font-semibold text-gray-800 font-mono">
                        ${prop.share_price?.toFixed(2)}/sh
                      </span>
                    </div>
                    {prop.reviewer && (
                      <div className="text-[10px] text-emerald-700 font-medium pt-1">
                        Reviewed by: {prop.reviewer}
                      </div>
                    )}
                  </div>

                  {prop.status === 'proposed' && (
                    <div className="mt-3 pt-2.5 border-t border-gray-100 flex items-center justify-between gap-2">
                      <select
                        onChange={(e) => onLinkInvestor(prop.id, e.target.value)}
                        className="bg-[#F4F6FC] border border-gray-200 rounded-lg px-2 py-1 text-[11px] text-gray-700 outline-none max-w-[150px] truncate"
                      >
                        <option value="">Link Investor...</option>
                        {investors.map((inv) => (
                          <option key={inv.id} value={inv.id}>
                            {inv.name}
                          </option>
                        ))}
                      </select>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => onRejectProposal(prop.id, reviewerName)}
                          className="px-2.5 py-1 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 text-xs font-bold transition-colors cursor-pointer"
                        >
                          Reject
                        </button>
                        <button
                          onClick={() => onApproveProposal(prop.id, reviewerName)}
                          className="px-3 py-1 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white text-xs font-bold transition-colors cursor-pointer shadow-2xs"
                        >
                          Approve
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Append-Only Cap Table Event Log Replay */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-3">
          <div>
            <h3 className="text-sm sm:text-base font-bold text-gray-900 flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#7048E8]" />
              <span>Append-Only Event Ledger ({events.length} Events)</span>
            </h3>
            <p className="text-xs text-gray-500">
              Deterministic state machine replaying all historical issuances, transfers, and redemptions.
            </p>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-[#F4F6FC] text-gray-600 border border-gray-200">
            Immutable Audit Trail
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-50/80 text-gray-500 font-semibold border-b border-gray-100">
              <tr>
                <th className="px-3 py-2.5">Timestamp</th>
                <th className="px-3 py-2.5">Action</th>
                <th className="px-3 py-2.5">Holder</th>
                <th className="px-3 py-2.5">Details / Transferee</th>
                <th className="px-3 py-2.5 text-right">Shares</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-gray-800">
              {events.map((ev) => (
                <tr key={ev.id} className="hover:bg-gray-50/60 transition-colors">
                  <td className="px-3 py-3 text-gray-500 font-mono whitespace-nowrap">
                    {new Date(ev.timestamp).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] uppercase font-bold ${
                        ev.event_type === 'issuance'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : ev.event_type === 'transfer'
                          ? 'bg-purple-50 text-[#7048E8] border border-purple-200'
                          : 'bg-amber-50 text-amber-700 border border-amber-200'
                      }`}
                    >
                      {ev.event_type}
                    </span>
                  </td>
                  <td className="px-3 py-3 font-semibold text-gray-900">{ev.holder_name}</td>
                  <td className="px-3 py-3 text-gray-600">
                    {ev.to_holder_name ? (
                      <span className="text-[#7048E8] font-semibold">Transferred to: {ev.to_holder_name}</span>
                    ) : (
                      `${ev.share_class} Shares`
                    )}
                  </td>
                  <td className="px-3 py-3 text-right font-mono font-bold text-gray-900">
                    {ev.share_count.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Record Event Modal */}
      {showEventModal && (
        <div className="fixed inset-0 z-50 bg-gray-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-gray-100 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl text-xs">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <h3 className="text-base font-bold text-gray-900">
                Record Cap Table Event
              </h3>
              <button
                onClick={() => setShowEventModal(false)}
                className="text-gray-400 hover:text-gray-600 cursor-pointer text-sm"
              >
                ✕
              </button>
            </div>

            {formError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600" />
                <span>{formError}</span>
              </div>
            )}

            <form onSubmit={handleCreateEvent} className="space-y-3">
              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">EVENT TYPE</label>
                <select
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value as CapTableEventType)}
                  className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                >
                  <option value="issuance">Issuance (New Shares)</option>
                  <option value="transfer">Transfer (Between Holders)</option>
                  <option value="cancellation">Cancellation (Forfeiture/Redemption)</option>
                </select>
              </div>

              <div>
                <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                  {eventType === 'transfer' ? 'TRANSFEROR (SOURCE HOLDER)' : 'HOLDER NAME'}
                </label>
                <input
                  type="text"
                  value={holderName}
                  onChange={(e) => setHolderName(e.target.value)}
                  placeholder="e.g. Horizon Ventures Fund"
                  className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                />
              </div>

              {eventType === 'transfer' && (
                <div>
                  <label className="block text-gray-500 font-semibold text-[11px] mb-1">
                    TRANSFEREE (RECIPIENT HOLDER)
                  </label>
                  <input
                    type="text"
                    value={toHolderName}
                    onChange={(e) => setToHolderName(e.target.value)}
                    placeholder="e.g. Secondary Buyer LLC"
                    className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                  />
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-500 font-semibold text-[11px] mb-1">SHARE QUANTITY</label>
                  <input
                    type="number"
                    value={shareCount}
                    onChange={(e) => setShareCount(parseInt(e.target.value, 10) || 0)}
                    className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 font-mono text-xs focus:border-[#7048E8] outline-none"
                  />
                </div>
                <div>
                  <label className="block text-gray-500 font-semibold text-[11px] mb-1">SHARE CLASS</label>
                  <select
                    value={shareClass}
                    onChange={(e) => setShareClass(e.target.value)}
                    className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-900 text-xs focus:border-[#7048E8] outline-none"
                  >
                    <option value="Common">Common</option>
                    <option value="Preferred">Preferred Series A</option>
                    <option value="Option">ESOP Option</option>
                    <option value="SAFE">SAFE Note</option>
                  </select>
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setShowEventModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-[#F4F6FC] hover:bg-gray-200 text-gray-700 text-xs font-semibold cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white font-bold text-xs shadow-xs cursor-pointer"
                >
                  Append Event to Ledger
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
