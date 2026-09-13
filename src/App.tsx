import React, { useState, useMemo, useEffect, useCallback } from 'react';
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
  LatestValuation,
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
import { Shield, Sparkles, AlertCircle, ExternalLink, Search, Bell, X } from 'lucide-react';
import * as liveApi from './services/api';

// True when the backend actively REJECTED the request (4xx). These are
// validation/compliance refusals (e.g. the 409A below-FMV gate), never
// outages -- surface the detail to the user and never demo-fall back
// (a silent fallback would fake a success). Network failures and 5xx
// keep the demo fallback.
function isClientRejection(err: unknown): err is liveApi.ApiRequestError {
  return (
    err instanceof liveApi.ApiRequestError &&
    err.status >= 400 &&
    err.status < 500
  );
}

export default function App() {
  // Default active tab to the modern dashboard requested by user
  const [activeTab, setActiveTab] = useState<string>('dashboard');

  // State Stores
  const [lastPipelineResult, setLastPipelineResult] = useState<PipelineRunResult | null>(null);
  const [capTableEvents, setCapTableEvents] = useState<CapTableEvent[]>(INITIAL_CAP_TABLE_EVENTS);
  // 409A context for the cap table (live API only; null in demo mode).
  const [latest409a, setLatest409a] = useState<LatestValuation | null>(null);
  // Backend rejection detail for the cap table (e.g. a 409A below-FMV gate
  // refusal). Rendered as a dismissible error box; demo fallback never runs
  // for these, because a compliance rejection is not an outage.
  const [errorBoxMsg, setErrorBoxMsg] = useState<string>('');
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

  // Live bootstrap: when the Python FastAPI backend is reachable, hydrate the
  // registries from the server instead of the demo seeds. On failure the demo
  // seeds stay and the app keeps running in demo mode.
  const refreshFromServer = useCallback(async () => {
    try {
      const [serverInvestors, serverCalls, serverProposals, latestValuation] = await Promise.all([
        liveApi.listInvestors(),
        liveApi.listCapitalCalls(),
        liveApi.listProposals(),
        // Never rejects -- null when no valuation is on file / offline.
        liveApi.getLatestValuation('Flowgate Systems Inc.'),
      ]);
      setInvestors(serverInvestors);
      setCapitalCalls(serverCalls);
      setProposals(serverProposals);
      setLatest409a(latestValuation);
    } catch {
      // Backend unreachable (or sleeping Render instance) -- demo mode.
    }
  }, []);

  // Hold the dashboard until the first hydration attempt settles, so its
  // mount-time useState copies contain live server data (or the demo seeds
  // when the backend is unreachable).
  const [bootstrapped, setBootstrapped] = useState(false);

  useEffect(() => {
    refreshFromServer().finally(() => setBootstrapped(true));
  }, [refreshFromServer]);

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

    // Re-pull the server-side registries so anything the pipeline persisted
    // (proposals, ledger, calls) shows up even if local merge missed it.
    void refreshFromServer();
  };

  // Handler: Record Event Manually (live-first: persists the security and
  // event on the backend; falls back to the local demo engine when offline)
  const handleRecordEvent = async (eventData: Omit<CapTableEvent, 'id' | 'timestamp'>) => {
    const traceId = generateTraceId();
    setErrorBoxMsg('');
    let newEvent: CapTableEvent = {
      ...eventData,
      id: 'cte_' + Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toISOString(),
    };

    if (liveApi.isLive()) {
      try {
        const [securityId] = await Promise.all([
          liveApi.ensureSecurity(eventData.issuer_name, eventData.share_class),
        ]);
        // Backend semantics: TRANSFER needs from_holder_id (source) and
        // holder_id (recipient); CANCELLATION needs from_holder_id; issuance
        // / exercise / conversion use holder_id. The frontend event model is
        // issuer/holder-centric where holder_id is the transferor for
        // transfers, so translate before hitting the API.
        const recipientId =
          eventData.event_type === 'transfer' && eventData.to_holder_name
            ? await liveApi.ensureHolder(eventData.to_holder_name)
            : undefined;
        const holderId =
          eventData.event_type === 'transfer'
            ? recipientId
            : eventData.event_type === 'cancellation'
            ? undefined
            : eventData.holder_name
            ? await liveApi.ensureHolder(eventData.holder_name)
            : undefined;
        const fromHolderId =
          eventData.event_type === 'transfer' || eventData.event_type === 'cancellation'
            ? await liveApi.ensureHolder(eventData.holder_name)
            : undefined;
        const evt = await liveApi.createCapTableEvent({
          security_id: securityId,
          event_type: eventData.event_type,
          holder_id: holderId,
          from_holder_id: fromHolderId,
          quantity: eventData.share_count,
          price_per_share: eventData.share_price ?? null,
          effective_date: new Date().toISOString(),
          // Vesting schedule fields (issuance only)
          vesting_start_date: eventData.vesting_start_date || null,
          vesting_period_months: eventData.vesting_period_months ?? null,
          cliff_months: eventData.cliff_months ?? null,
          acceleration_clause: eventData.acceleration_clause || null,
          // Repurchase fields (cancellation only)
          is_repurchase: Boolean(eventData.is_repurchase),
          repurchase_approver:
            eventData.is_repurchase && eventData.repurchase_approver
              ? eventData.repurchase_approver
              : null,
        });
        newEvent = {
          ...evt,
          issuer_name: eventData.issuer_name,
          holder_name: eventData.holder_name,
          to_holder_name: eventData.to_holder_name,
          // Keep the frontend event model (holder_id = transferor for
          // transfers) consistent with the demo engine, even though the
          // backend returns the recipient as holder_id for transfers.
          holder_id: eventData.holder_id || evt.holder_id,
          to_holder_id: eventData.to_holder_id,
          share_count: eventData.share_count,
          share_class: eventData.share_class,
          share_price: eventData.share_price ?? evt.share_price,
          vesting_start_date:
            eventData.vesting_start_date || evt.vesting_start_date,
          vesting_period_months:
            eventData.vesting_period_months ?? evt.vesting_period_months,
          cliff_months: eventData.cliff_months ?? evt.cliff_months,
          acceleration_clause:
            eventData.acceleration_clause || evt.acceleration_clause,
          is_repurchase: Boolean(eventData.is_repurchase),
          repurchase_approver:
            eventData.repurchase_approver || evt.repurchase_approver,
        };
      } catch (err) {
        if (isClientRejection(err)) {
          // The backend REJECTED the event (validation, 409A below-FMV
          // gate, ...). Never demo-fall back for a compliance rejection:
          // surface the detail and leave the ledger untouched.
          setErrorBoxMsg(err.message);
          return;
        }
        // Network failure or 5xx -- demo fallback below.
      }
    }

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

  // Handler: Approve Cap Table Proposal (live-first: the backend gate
  // materializes the issuance; local mirror keeps the view in sync)
  const handleApproveProposal = async (proposalId: string, reviewer: string) => {
    const prop = proposals.find((p) => p.id === proposalId);
    if (!prop || prop.status !== 'proposed') return;

    if (liveApi.isLive()) {
      try {
        await liveApi.approveProposal(proposalId, reviewer);
      } catch (err) {
        if (isClientRejection(err)) {
          // Backend REJECTED the approval (review gate, already reviewed,
          // ...) -- surface it, never fake success locally.
          setErrorBoxMsg(err.message);
          return;
        }
        // Network failure or 5xx -- demo fallback below.
      }
    }

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

  // Handler: Reject Cap Table Proposal (live-first)
  const handleRejectProposal = async (proposalId: string, reviewer: string) => {
    if (liveApi.isLive()) {
      try {
        await liveApi.rejectProposal(proposalId, reviewer);
      } catch (err) {
        if (isClientRejection(err)) {
          // Backend REJECTED the rejection -- surface it, never fake
          // success locally.
          setErrorBoxMsg(err.message);
          return;
        }
        // Network failure or 5xx -- demo fallback below.
      }
    }

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

  // Handler: Link Investor to Proposal (live-first)
  const handleLinkInvestor = async (proposalId: string, investorId: string) => {
    const inv = investors.find((i) => i.id === investorId);
    if (!inv) return;

    if (liveApi.isLive()) {
      try {
        await liveApi.linkInvestor(proposalId, investorId, 'M. Vance — Audit Lead');
      } catch (err) {
        if (isClientRejection(err)) {
          // Backend REJECTED the link (unknown investor/proposal, ...)
          // -- surface it, never fake success locally.
          setErrorBoxMsg(err.message);
          return;
        }
        // Network failure or 5xx -- demo fallback below.
      }
    }

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

  // Handler: Create Capital Call (live-first: persists against the demo fund
  // instrument on the backend; falls back to a local demo call)
  const handleCreateCapitalCall = async (
    callData: Omit<CapitalCall, 'id' | 'created_at' | 'status'>
  ) => {
    (async () => {
      if (liveApi.isLive()) {
        try {
          const created = await liveApi.createCapitalCall({
            funder_name: callData.funder_name,
            currency: callData.currency,
            capital_owing: callData.capital_owing,
            due_date: callData.due_date || null,
            wire_details: callData.wire_details || null,
          });
          setCapitalCalls((prev) => [created, ...prev]);

          const entry: LedgerEntry = {
            id: 'led_' + Math.random().toString(36).substring(2, 9),
            entry_type: 'capital_call_review',
            trace_id: generateTraceId(),
            title: `Capital Call Issued: ${created.capital_owing.toLocaleString()} ${created.currency} to ${created.funder_name}`,
            details: {
              due_date: created.due_date,
              wire_details: created.wire_details,
            },
            timestamp: new Date().toISOString(),
          };

          setLedgerEntries((prev) => [entry, ...prev]);
          return;
        } catch (err) {
          if (isClientRejection(err)) {
            // Backend REJECTED the call (validation, unknown funder, ...)
            // -- surface it, never add a demo call that looks accepted.
            setErrorBoxMsg(err.message);
            return;
          }
          // Network failure or 5xx -- demo fallback below.
        }
      }

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
    })();
  };

  // Handler: Review Capital Call (live-first)
  const handleReviewCapitalCall = async (
    callId: string,
    status: 'approved' | 'rejected',
    reviewer: string
  ) => {
    (async () => {
      if (liveApi.isLive()) {
        try {
          const updated = await liveApi.reviewCapitalCall(
            callId,
            reviewer,
            status === 'approved' ? 'approve' : 'reject'
          );
          setCapitalCalls((prev) =>
            prev.map((c) =>
              c.id === callId
                ? {
                    ...c,
                    ...updated,
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
            details: { call_id: updated.id, reviewer, status },
            timestamp: new Date().toISOString(),
          };

          setLedgerEntries((prev) => [entry, ...prev]);
          return;
        } catch (err) {
          if (isClientRejection(err)) {
            // Backend REJECTED the review (already reviewed, unknown call,
            // ...) -- surface it, never fake success locally.
            setErrorBoxMsg(err.message);
            return;
          }
          // Network failure or 5xx -- demo fallback below.
        }
      }

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
    })();
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
          {/* Global backend-rejection banner (4xx from any live handler:
              409A gate, review gates, validation). Visible in every tab. */}
          {errorBoxMsg && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3.5 text-xs text-red-700 flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                <span>{errorBoxMsg}</span>
              </div>
              <button onClick={() => setErrorBoxMsg('')} className="text-red-500 hover:text-red-700 cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {activeTab === 'dashboard' && bootstrapped && (
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
                latest409a={latest409a}
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
                onRefreshCalls={refreshFromServer}
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
