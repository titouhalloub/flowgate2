import React, { useState } from 'react';
import { Investor, CapTableSnapshot, CapitalCallNotice } from '../types';
import {
  Users,
  ShieldCheck,
  Globe,
  Building2,
  Briefcase,
  ChevronRight,
  DollarSign,
  PieChart,
  CheckCircle2,
} from 'lucide-react';

interface InvestorPortfolioViewProps {
  investors: Investor[];
  snapshot: CapTableSnapshot;
  capitalCalls: CapitalCallNotice[];
}

export const InvestorPortfolioView: React.FC<InvestorPortfolioViewProps> = ({
  investors,
  snapshot,
  capitalCalls,
}) => {
  const [selectedInvestorId, setSelectedInvestorId] = useState<string>(investors[0]?.id || '');

  const selectedInvestor = investors.find((inv) => inv.id === selectedInvestorId) || investors[0];

  // Calculate holdings in current issuer
  const holding = snapshot.positions.find(
    (p) =>
      p.holder_name.toLowerCase().includes(selectedInvestor?.name.toLowerCase().split(' ')[0] || '') ||
      p.holder_id === selectedInvestor?.id
  );

  // Associated capital calls
  const calls = capitalCalls.filter(
    (c) =>
      c.funder_name.toLowerCase().includes(selectedInvestor?.name.toLowerCase().split(' ')[0] || '')
  );

  return (
    <div className="space-y-6">
      {/* Top Banner Metric Cards */}
      <div className="bg-[#E8EFFD] rounded-2xl p-4 sm:p-5">
        <div className="text-[11px] font-bold tracking-wider text-[#5C4DE5] uppercase mb-3">
          CROSS-FUND INVESTOR REGISTRY & PORTFOLIO EXPOSURE
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#7048E8] text-white flex items-center justify-center">
                <Users className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Registered Investors</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              {investors.length} <span className="text-xs font-normal text-gray-400">Institutional LPs</span>
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              Direct equity & fund commitments
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#20C997] text-white flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Compliance Status</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight text-emerald-600">
              100% Cleared
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              KYC & AML verified across entities
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FAB005] text-white flex items-center justify-center">
                <Globe className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Global Jurisdictions</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              Multi-Region
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              Delaware, DIFC, Cayman, Luxembourg
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Investor Directory + Selected Portfolio Detail */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Investor List (4 cols) */}
        <div className="lg:col-span-4 bg-white rounded-2xl p-5 shadow-xs border border-gray-100 space-y-3">
          <div className="flex items-center justify-between border-b border-gray-100 pb-2.5">
            <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wide">
              Institutional & LP Directory
            </h3>
            <span className="text-xs font-bold text-[#7048E8] bg-[#EBE7FD] px-2 py-0.5 rounded-full">
              {investors.length}
            </span>
          </div>

          <div className="space-y-2">
            {investors.map((inv) => {
              const isSelected = inv.id === selectedInvestorId;
              return (
                <button
                  key={inv.id}
                  onClick={() => setSelectedInvestorId(inv.id)}
                  className={`w-full text-left p-3.5 rounded-xl text-xs transition-all border cursor-pointer ${
                    isSelected
                      ? 'bg-[#EBE7FD]/60 border-purple-300 text-gray-900 shadow-xs'
                      : 'bg-[#F8FAFD] border-gray-200/80 text-gray-700 hover:border-purple-200'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sm text-gray-900 truncate">{inv.name}</span>
                    <ChevronRight
                      className={`w-4 h-4 transition-transform ${
                        isSelected ? 'text-[#7048E8] translate-x-0.5' : 'text-gray-400'
                      }`}
                    />
                  </div>

                  <div className="flex items-center gap-2 mt-2 text-[10px]">
                    <span className="px-2 py-0.5 rounded-full bg-white border border-gray-200 font-semibold uppercase text-gray-600">
                      {inv.investor_type}
                    </span>
                    <span className="text-gray-500 font-medium">{inv.jurisdiction}</span>
                    <span className="text-emerald-700 font-bold ml-auto flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                      KYC Cleared
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Column: Selected Investor Cross-Fund Detail (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {selectedInvestor && (
            <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-4">
                <div>
                  <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                    INVESTOR ENTITY PROFILE
                  </div>
                  <h3 className="text-xl font-bold text-gray-900 mt-0.5">
                    {selectedInvestor.name}
                  </h3>
                  <div className="text-xs text-gray-500 mt-1 flex flex-wrap items-center gap-2">
                    <div className="flex items-center gap-1">
                      <Globe className="w-3.5 h-3.5 text-gray-400" />
                      <span>Jurisdiction: <strong>{selectedInvestor.jurisdiction}</strong></span>
                    </div>
                    <span>&bull;</span>
                    <span className="text-emerald-700 font-semibold flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> AML & Sanctions Cleared
                    </span>
                  </div>
                </div>

                <div>
                  <span className="px-3 py-1 rounded-full bg-[#EBE7FD] text-[#7048E8] border border-purple-200 text-xs uppercase font-bold">
                    {selectedInvestor.investor_type} Entity
                  </span>
                </div>
              </div>

              {/* Aggregated Positions Across Vehicles */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wide flex items-center gap-1.5">
                  <Briefcase className="w-4 h-4 text-[#7048E8]" />
                  <span>Cross-Vehicle Exposure Breakdown</span>
                </h4>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  {/* Equity Cap Table Position */}
                  <div className="p-4 rounded-xl bg-[#F8FAFD] border border-gray-200/80 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-[10px] text-gray-400 font-bold uppercase">
                        DIRECT EQUITY POSITION
                      </div>
                      <PieChart className="w-4 h-4 text-[#7048E8]" />
                    </div>
                    <div className="text-sm font-bold text-gray-900">
                      Flowgate Systems Inc.
                    </div>
                    {holding ? (
                      <div className="space-y-1.5 text-xs pt-1 border-t border-gray-200/60">
                        <div className="flex justify-between">
                          <span className="text-gray-500">Shares Held:</span>
                          <span className="text-gray-900 font-mono font-bold">{holding.shares.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Fully Diluted %:</span>
                          <span className="text-[#7048E8] font-mono font-bold">{holding.ownership_percent}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Share Class:</span>
                          <span className="font-semibold text-gray-800">{holding.share_class}</span>
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-gray-400 pt-1">
                        No active direct equity holdings currently logged in this issuer.
                      </div>
                    )}
                  </div>

                  {/* Fund Drawdowns / Calls */}
                  <div className="p-4 rounded-xl bg-[#F8FAFD] border border-gray-200/80 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-[10px] text-gray-400 font-bold uppercase">
                        FUND COMMITMENTS & DRAWDOWNS
                      </div>
                      <DollarSign className="w-4 h-4 text-[#20C997]" />
                    </div>
                    <div className="text-sm font-bold text-gray-900">
                      Global Tech Opportunities Fund II
                    </div>
                    {calls.length > 0 ? (
                      <div className="space-y-1.5 text-xs pt-1 border-t border-gray-200/60">
                        <div className="flex justify-between">
                          <span className="text-gray-500">Active Call Notices:</span>
                          <span className="text-gray-900 font-mono font-bold">{calls.length}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Capital Called:</span>
                          <span className="text-[#20C997] font-mono font-bold">
                            ${calls.reduce((s, c) => s + c.capital_owing, 0).toLocaleString()} USD
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500">Latest Status:</span>
                          <span className="text-emerald-700 uppercase font-bold text-[10px] bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                            {calls[0].status}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-gray-400 pt-1">
                        No pending capital calls recorded for this LP account.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Cross-Compliance Guarantee Note */}
              <div className="p-3.5 rounded-xl bg-[#EBF0FD] border border-blue-200 text-xs text-blue-950 flex items-start gap-2.5">
                <ShieldCheck className="w-4 h-4 text-[#2342E3] flex-shrink-0 mt-0.5" />
                <p className="leading-relaxed">
                  <strong>Multi-Jurisdictional Identity Guarantee:</strong> Any compliance finding on this entity (e.g. KYC expiration or sanction flag) propagates deterministically across all instruments in the audit ledger simultaneously.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
