import React, { useState, useMemo } from 'react';
import { ModernSidebar } from './components/ModernSidebar';
import { FlowgateDashboard } from './components/FlowgateDashboard';
import { PipelineView } from './components/PipelineView';
import { CapTableView } from './components/CapTableView';
import { CapitalCallsView } from './components/CapitalCallsView';
import { InvestorPortfolioView } from './components/InvestorPortfolioView';
import { AuditLedgerView } from './components/AuditLedgerView';
import { DocsView } from './components/DocsView';
import {
  CapTableEvent,
  CapTableProposal,
  CapitalCall,
  Investor,
  LedgerEntry,
  PipelineRunResult,
} from './types';
import {
  INITIAL_CAP_TABLE_EVENTS,
  INITIAL_CAPITAL_CALLS,
  INITIAL_INVESTORS,
  computeCapTable,
  generateTraceId,
} from './services/flowgateEngine';
import { Shield, Sparkles, AlertCircle, ExternalLink, Search, Bell } from 'lucide-react';

export default function App() {
  // Default active tab to the modern dashboard requested by user
  const [activeTab, setActiveTab] = useState<string>('dashboard');

  // State Stores
  const [lastPipelineResult, setLastPipelineResult] = useState<PipelineRunResult | null>(null);
  const [capTableEvents, setCapTableEvents] = useState<CapTableEvent[]>(INITIAL_CAP_TABLE_EVENTS);
  const [proposals, setProposals] = useState<CapTableProposal[]>([
    {
      id: 'prop_seed_1',
      document_id: 'doc_seed_sub',
      issuer_name: 'Flowgate Systems Inc.',
      holder_name: 'Apex Horizon Growth Fund LP',
      share_count: 150000,
      share_class: 'Common',
      share_price: 12.5,
      status: 'proposed',
      created_at: new Date(Date.now() - 3600000).toISOString(),
    },
  ]);
  const [capitalCalls, setCapitalCalls] = useState<CapitalCall[]>(INITIAL_CAPITAL_CALLS);
  const [investors, setInvestors] = useState<Investor[]>(INITIAL_INVESTORS);

  const [ledgerEntries, setLedgerEntries] = useState<LedgerEntry[]>([
    {
      id: 'led_init_01',
      entry_type: 'cap_table_event',
      trace_id: generateTraceId(),
      title: 'Cap Table Genesis: Founder Issuances Replayed',
      details: {
        founders: ['Tariq Al-Mansoor', 'Elena Rostova'],
        total_shares: 850000,
      },
      timestamp: '2025-06-01T09:00:00Z',
    },
    {
      id: 'led_init_02',
      entry_type: 'cap_table_event',
      trace_id: generateTraceId(),
      title: 'Option Pool Creation (ESOP 150k shares)',
      details: {
        pool_size: 150000,
        class: 'Option',
      },
      timestamp: '2025-08-15T12:00:00Z',
    },
    {
      id: 'led_init_03',
      entry_type: 'capital_call_review',
      trace_id: generateTraceId(),
      title: 'Capital Call Cleared: Sovereign Wealth Asset Management',
      details: {
        amount: 1200000,
        reviewer: 'Audit Lead M. Vance',
      },
      timestamp: '2026-08-10T11:00:00Z',
    },
  ]);

  // Derived Event-Sourced Cap Table
  const capTableSnapshot = useMemo(() => {
    return computeCapTable(capTableEvents, 'Flowgate Systems Inc.');
  }, [capTableEvents]);

  // Handler: Pipeline Run Completed
  const handlePipelineCompleted = (result: PipelineRunResult) => {
    setLastPipelineResult(result);
    setLedgerEntries((prev) => [...result.ledger_entries, ...prev]);

    if (result.proposal_created) {
      setProposals((prev) => [result.proposal_created!, ...prev]);
    }
  };

  // Handler: Record Event Manually
  const handleRecordEvent = (eventData: Omit<CapTableEvent, 'id' | 'timestamp'>) => {
    const traceId = generateTraceId();
    const newEvent: CapTableEvent = {
      ...eventData,
      id: 'cte_' + Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toISOString(),
    };

    setCapTableEvents((prev) => [...prev, newEvent]);

    const entry: LedgerEntry = {
      id: 'led_' + Math.random().toString(36).substring(2, 9),
      entry_type: 'cap_table_event',
      trace_id: traceId,
      title: `Cap Table Mutation: ${newEvent.event_type.toUpperCase()} for ${newEvent.holder_name}`,
      details: {
        shares: newEvent.share_count,
        class: newEvent.share_class,
        to_holder: newEvent.to_holder_name,
      },
      timestamp: new Date().toISOString(),
    };

    setLedgerEntries((prev) => [entry, ...prev]);
  };

  // Handler: Approve Cap Table Proposal
  const handleApproveProposal = (proposalId: string, reviewer: string) => {
    const prop = proposals.find((p) => p.id === proposalId);
    if (!prop || prop.status !== 'proposed') return;

    setProposals((prev) =>
      prev.map((p) =>
        p.id === proposalId
          ? {
              ...p,
              status: 'approved',
              reviewer,
              reviewed_at: new Date().toISOString(),
            }
          : p
      )
    );

    // Materialize into Cap Table Event
    const traceId = generateTraceId();
    const newEvent: CapTableEvent = {
      id: 'cte_' + Math.random().toString(36).substring(2, 9),
      issuer_name: prop.issuer_name,
      event_type: 'issuance',
      holder_id: prop.investor_id || 'inv_' + prop.holder_name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
      holder_name: prop.holder_name,
      share_count: prop.share_count,
      share_class: prop.share_class,
      share_price: prop.share_price,
      timestamp: new Date().toISOString(),
    };

    setCapTableEvents((prev) => [...prev, newEvent]);

    const entry: LedgerEntry = {
      id: 'led_' + Math.random().toString(36).substring(2, 9),
      entry_type: 'cap_table_event',
      trace_id: traceId,
      title: `Proposal Approved: ${prop.share_count.toLocaleString()} shares issued to ${prop.holder_name}`,
      details: {
        reviewer,
        proposal_id: proposalId,
        share_price: prop.share_price,
      },
      timestamp: new Date().toISOString(),
    };

    setLedgerEntries((prev) => [entry, ...prev]);
  };

  // Handler: Reject Cap Table Proposal
  const handleRejectProposal = (proposalId: string, reviewer: string) => {
    setProposals((prev) =>
      prev.map((p) =>
        p.id === proposalId
          ? {
              ...p,
              status: 'rejected',
              reviewer,
              reviewed_at: new Date().toISOString(),
            }
          : p
      )
    );

    const entry: LedgerEntry = {
      id: 'led_' + Math.random().toString(36).substring(2, 9),
      entry_type: 'cap_table_event',
      trace_id: generateTraceId(),
      title: `Proposal Rejected by ${reviewer}`,
      details: { proposal_id: proposalId },
      timestamp: new Date().toISOString(),
    };

    setLedgerEntries((prev) => [entry, ...prev]);
  };

  // Handler: Link Investor to Proposal
  const handleLinkInvestor = (proposalId: string, investorId: string) => {
    const inv = investors.find((i) => i.id === investorId);
    if (!inv) return;

    setProposals((prev) =>
      prev.map((p) =>
        p.id === proposalId
          ? {
              ...p,
              investor_id: investorId,
              holder_name: inv.name,
            }
          : p
      )
    );
  };

  // Handler: Create Capital Call
  const handleCreateCapitalCall = (
    callData: Omit<CapitalCall, 'id' | 'created_at' | 'status'>
  ) => {
    const newCall: CapitalCall = {
      ...callData,
      id: 'call_' + Math.random().toString(36).substring(2, 9),
      status: 'pending_approval',
      created_at: new Date().toISOString(),
    };

    setCapitalCalls((prev) => [newCall, ...prev]);

    const entry: LedgerEntry = {
      id: 'led_' + Math.random().toString(36).substring(2, 9),
      entry_type: 'capital_call_review',
      trace_id: generateTraceId(),
      title: `Capital Call Issued: ${newCall.capital_owing.toLocaleString()} ${newCall.currency} to ${newCall.funder_name}`,
      details: {
        due_date: newCall.due_date,
        wire_details: newCall.wire_details,
      },
      timestamp: new Date().toISOString(),
    };

    setLedgerEntries((prev) => [entry, ...prev]);
  };

  // Handler: Review Capital Call
  const handleReviewCapitalCall = (
    callId: string,
    status: 'approved' | 'rejected',
    reviewer: string
  ) => {
    setCapitalCalls((prev) =>
      prev.map((c) =>
        c.id === callId
          ? {
              ...c,
              status,
              reviewer,
              reviewed_at: new Date().toISOString(),
            }
          : c
      )
    );

    const entry: LedgerEntry = {
      id: 'led_' + Math.random().toString(36).substring(2, 9),
      entry_type: 'capital_call_review',
      trace_id: generateTraceId(),
      title: `Capital Call ${status.toUpperCase()} by ${reviewer}`,
      details: { call_id: callId, reviewer, status },
      timestamp: new Date().toISOString(),
    };

    setLedgerEntries((prev) => [entry, ...prev]);
  };

  const pendingProposalCount = proposals.filter((p) => p.status === 'proposed').length;
  const pendingCapitalCallCount = capitalCalls.filter((c) => c.status === 'pending_approval').length;

  return (
    <div className="min-h-screen bg-[#F4F6FB] flex flex-row selection:bg-[#7048E8] selection:text-white font-sans">
      {/* Left Vertical Modern Sidebar matching screenshot */}
      <ModernSidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        proposalCount={pendingProposalCount}
        capitalCallPendingCount={pendingCapitalCallCount}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-x-hidden">
        {/* Subtle Top Utility Bar */}
        <header className="px-6 py-3.5 flex items-center justify-between border-b border-gray-100 bg-white/50 backdrop-blur-xs">
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold text-gray-800">
              Flowgate <span className="text-gray-400 font-normal">/</span> San Jose Shark
            </span>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
              Deterministic Engine
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#F4F6FB] text-gray-400 text-xs border border-gray-200/60 w-52">
              <Search className="w-3.5 h-3.5 text-gray-400" />
              <span>Search transactions...</span>
            </div>

            <div className="text-xs font-semibold text-gray-500 bg-white px-3 py-1.5 rounded-lg border border-gray-100 shadow-2xs">
              Live v0.1.0
            </div>
          </div>
        </header>

        {/* Dynamic View Container */}
        <main className="flex-1 p-4 sm:p-7 max-w-7xl w-full mx-auto">
          {activeTab === 'dashboard' && (
            <FlowgateDashboard
              initialEvents={capTableEvents}
              initialProposals={proposals}
              initialCapitalCalls={capitalCalls}
              initialInvestors={investors}
              initialLedger={ledgerEntries}
            />
          )}

          {activeTab === 'pipeline' && (
            <div className="space-y-6">
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-gray-900 tracking-tight">Confidence-Gated Intake Pipeline</h2>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#EBF0FD] text-[#2342E3] border border-blue-200/60">
                      Intake & Verification
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Classify, extract, and verify Islamic & Traditional compliance rules with automated confidence triage
                  </p>
                </div>
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 transition-colors cursor-pointer"
                >
                  Back to Dashboard
                </button>
              </div>
              <PipelineView
                onPipelineCompleted={handlePipelineCompleted}
                lastResult={lastPipelineResult}
              />
            </div>
          )}

          {activeTab === 'captable' && (
            <div className="space-y-6">
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-gray-900 tracking-tight">Event-Sourced Cap Table & Human Review Gate</h2>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#EBE7FD] text-[#7048E8] border border-purple-200/60">
                      Equity Ledger
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Replayed append-only ledger with proposal authorization and strict overdraft prevention
                  </p>
                </div>
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 transition-colors cursor-pointer"
                >
                  Back to Dashboard
                </button>
              </div>
              <CapTableView
                snapshot={capTableSnapshot}
                events={capTableEvents}
                proposals={proposals}
                investors={investors}
                onRecordEvent={handleRecordEvent}
                onApproveProposal={handleApproveProposal}
                onRejectProposal={handleRejectProposal}
                onLinkInvestor={handleLinkInvestor}
              />
            </div>
          )}

          {activeTab === 'capitalcalls' && (
            <div className="space-y-6">
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-gray-900 tracking-tight">Capital Calls & Drawdown Management</h2>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#E8EFFD] text-[#5C4DE5] border border-indigo-200/60">
                      Drawdowns & Wire
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Ingest LP capital calls, verify payment statuses, and monitor overdue deadlines
                  </p>
                </div>
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 transition-colors cursor-pointer"
                >
                  Back to Dashboard
                </button>
              </div>
              <CapitalCallsView
                capitalCalls={capitalCalls}
                onCreateCall={handleCreateCapitalCall}
                onReviewCall={handleReviewCapitalCall}
              />
            </div>
          )}

          {activeTab === 'investors' && (
            <div className="space-y-6">
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-gray-900 tracking-tight">Cross-Fund Investor Portfolio</h2>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#EBF0FD] text-[#2342E3] border border-blue-200/60">
                      Unified Registry
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Multi-vehicle exposure breakdown, debt instruments, and KYC/AML verified standing
                  </p>
                </div>
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 transition-colors cursor-pointer"
                >
                  Back to Dashboard
                </button>
              </div>
              <InvestorPortfolioView
                investors={investors}
                snapshot={capTableSnapshot}
                capitalCalls={capitalCalls}
              />
            </div>
          )}

          {activeTab === 'ledger' && (
            <div className="space-y-6">
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-gray-900 tracking-tight">Unified Append-Only Audit Ledger</h2>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Cryptographic Traceability
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Immutable audit log of all document intake decisions, compliance checks, and cap table updates
                  </p>
                </div>
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 transition-colors cursor-pointer"
                >
                  Back to Dashboard
                </button>
              </div>
              <AuditLedgerView ledgerEntries={ledgerEntries} />
            </div>
          )}

          {activeTab === 'repo' && (
            <div className="space-y-6">
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-gray-900 tracking-tight">Repository & Architectural Documentation</h2>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#EBE7FD] text-[#7048E8] border border-purple-200/60">
                      Docs & Code
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Positioning, roadmap specifications, schema blueprints, and core engine code
                  </p>
                </div>
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200 transition-colors cursor-pointer"
                >
                  Back to Dashboard
                </button>
              </div>
              <DocsView />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
