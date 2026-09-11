import React, { useState } from 'react';
import { LedgerEntry, LedgerEntryType } from '../types';
import { ShieldCheck, Filter, Clock, Hash, CheckCircle2, Search, FileText, Layers, Lock } from 'lucide-react';

interface AuditLedgerViewProps {
  ledgerEntries: LedgerEntry[];
}

export const AuditLedgerView: React.FC<AuditLedgerViewProps> = ({ ledgerEntries }) => {
  const [filterType, setFilterType] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');

  const filtered = ledgerEntries.filter((entry) => {
    if (filterType !== 'all' && entry.entry_type !== filterType) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const inTitle = entry.title.toLowerCase().includes(term);
      const inTrace = entry.trace_id.toLowerCase().includes(term);
      const inType = entry.entry_type.toLowerCase().includes(term);
      if (!inTitle && !inTrace && !inType) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Top Banner Metric Cards */}
      <div className="bg-[#E8EFFD] rounded-2xl p-4 sm:p-5">
        <div className="text-[11px] font-bold tracking-wider text-[#5C4DE5] uppercase mb-3">
          UNIFIED AUDIT LEDGER & REPLAY SYSTEM
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#7048E8] text-white flex items-center justify-center">
                <Layers className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Ledger Records</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              {ledgerEntries.length} <span className="text-xs font-normal text-gray-400">Events</span>
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              Deterministic append-only records
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#20C997] text-white flex items-center justify-center">
                <Lock className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Immutability Guarantee</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight text-emerald-600">
              Append-Only
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              No in-place updates or deletions permitted
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FAB005] text-white flex items-center justify-center">
                <Hash className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Cryptographic Trace</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              Unique Trace IDs
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              Linked across documents and cap table states
            </div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white rounded-2xl p-4 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 flex-1 max-w-md bg-[#F4F6FC] px-3 py-2 rounded-xl border border-gray-200">
          <Search className="w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by title, trace ID, or keyword..."
            className="w-full bg-transparent text-gray-900 focus:outline-none placeholder-gray-400 text-xs"
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-gray-400 uppercase font-bold text-[10px]">FILTER:</span>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-[#F4F6FC] border border-gray-200 rounded-xl px-3 py-2 text-xs text-gray-700 font-semibold focus:border-[#7048E8] outline-none cursor-pointer"
          >
            <option value="all">All Event Types</option>
            <option value="document_result">Document Intake</option>
            <option value="compliance_event">Compliance Decisions</option>
            <option value="cap_table_event">Cap Table Mutations</option>
            <option value="capital_call_review">Capital Call Reviews</option>
          </select>
        </div>
      </div>

      {/* Event Timeline Entries */}
      <div className="space-y-3 text-xs">
        {filtered.length === 0 ? (
          <div className="p-8 text-center bg-white rounded-2xl border border-gray-100 shadow-xs text-gray-400">
            No ledger entries matching current filter.
          </div>
        ) : (
          filtered.map((entry) => (
            <div
              key={entry.id}
              className="bg-white border border-gray-100 hover:border-purple-200 rounded-2xl p-5 shadow-xs transition-colors space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-3">
                <div className="flex items-center gap-2.5">
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] uppercase font-bold ${
                      entry.entry_type === 'compliance_event'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : entry.entry_type === 'cap_table_event'
                        ? 'bg-[#EBE7FD] text-[#7048E8] border border-purple-200'
                        : entry.entry_type === 'capital_call_review'
                        ? 'bg-amber-50 text-amber-700 border border-amber-200'
                        : 'bg-blue-50 text-blue-700 border border-blue-200'
                    }`}
                  >
                    {entry.entry_type.replace(/_/g, ' ')}
                  </span>
                  <span className="font-bold text-sm text-gray-900">{entry.title}</span>
                </div>

                <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
                  <Clock className="w-3.5 h-3.5" />
                  <span>
                    {new Date(entry.timestamp).toLocaleTimeString()} &bull; {new Date(entry.timestamp).toLocaleDateString()}
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-1.5">
                  <Hash className="w-3.5 h-3.5 text-gray-400" />
                  <span className="text-gray-500">Trace ID:</span>
                  <span className="font-mono font-bold text-[#7048E8] bg-[#F4F6FC] px-2 py-0.5 rounded-lg border border-gray-200">
                    {entry.trace_id}
                  </span>
                </div>

                {entry.instrument_id && (
                  <div className="text-gray-500">
                    Instrument: <span className="font-mono font-semibold text-gray-800">{entry.instrument_id}</span>
                  </div>
                )}
              </div>

              {/* JSON Payload Details */}
              {entry.details && Object.keys(entry.details).length > 0 && (
                <pre className="p-3 rounded-xl bg-[#F8FAFD] border border-gray-200/70 text-[11px] font-mono text-gray-700 overflow-x-auto">
                  {JSON.stringify(entry.details, null, 2)}
                </pre>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
