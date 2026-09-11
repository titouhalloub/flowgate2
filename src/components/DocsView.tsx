import React, { useState } from 'react';
import { BookOpen, Code, FileText, CheckCircle2, GitBranch, ArrowRight, Layers, ShieldCheck, ExternalLink } from 'lucide-react';

export const DocsView: React.FC = () => {
  const [activeDoc, setActiveDoc] = useState<'positioning' | 'captable' | 'capitalcalls' | 'python_code'>('positioning');

  return (
    <div className="space-y-6">
      {/* Top Banner Metric Cards */}
      <div className="bg-[#E8EFFD] rounded-2xl p-4 sm:p-5 overflow-hidden">
        <div className="text-[11px] font-bold tracking-wider text-[#5C4DE5] uppercase mb-3">
          SYSTEM DOCUMENTATION & SPECIFICATIONS
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between min-w-0 overflow-hidden">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-lg bg-[#7048E8] text-white flex items-center justify-center shrink-0">
                <BookOpen className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500 truncate">Core Positioning</span>
            </div>
            <div className="text-lg sm:text-xl font-extrabold text-[#111827] mt-3 tracking-tight truncate">
              Shared Pipeline
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium truncate">
              Private-capital compliance & ledger infrastructure
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between min-w-0 overflow-hidden">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-lg bg-[#20C997] text-white flex items-center justify-center shrink-0">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500 truncate">Compliance Logic</span>
            </div>
            <div className="text-lg sm:text-xl font-extrabold text-[#111827] mt-3 tracking-tight text-emerald-600 truncate">
              Rules as Data
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium truncate">
              Dual-track Islamic & Traditional gateway
            </div>
          </div>

          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between min-w-0 overflow-hidden">
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded-lg bg-[#FAB005] text-white flex items-center justify-center shrink-0">
                <GitBranch className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500 truncate">Open Repository</span>
            </div>
            <a
              href="https://github.com/titouhalloub/flowgate"
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center justify-between gap-1 mt-3 min-w-0"
              title="titouhalloub/flowgate on GitHub"
            >
              <span className="text-sm sm:text-base lg:text-lg font-extrabold text-[#111827] group-hover:text-[#7048E8] tracking-tight truncate transition-colors">
                titouhalloub/flowgate
              </span>
              <ExternalLink className="w-3.5 h-3.5 text-gray-400 group-hover:text-[#7048E8] shrink-0 transition-colors" />
            </a>
            <div className="text-[11px] text-gray-400 mt-1 font-medium truncate">
              Python/SQLAlchemy + React Engine
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex gap-2 border-b border-gray-200/80 pb-2 overflow-x-auto text-xs">
        <button
          onClick={() => setActiveDoc('positioning')}
          className={`px-3.5 py-2 rounded-xl flex items-center gap-2 transition-all cursor-pointer ${
            activeDoc === 'positioning'
              ? 'bg-[#7048E8] text-white font-bold shadow-xs'
              : 'bg-white hover:bg-gray-50 text-gray-600 border border-gray-200/80'
          }`}
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span>POSITIONING.md</span>
        </button>

        <button
          onClick={() => setActiveDoc('captable')}
          className={`px-3.5 py-2 rounded-xl flex items-center gap-2 transition-all cursor-pointer ${
            activeDoc === 'captable'
              ? 'bg-[#7048E8] text-white font-bold shadow-xs'
              : 'bg-white hover:bg-gray-50 text-gray-600 border border-gray-200/80'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>CAPTABLE-ROADMAP.md</span>
        </button>

        <button
          onClick={() => setActiveDoc('capitalcalls')}
          className={`px-3.5 py-2 rounded-xl flex items-center gap-2 transition-all cursor-pointer ${
            activeDoc === 'capitalcalls'
              ? 'bg-[#7048E8] text-white font-bold shadow-xs'
              : 'bg-white hover:bg-gray-50 text-gray-600 border border-gray-200/80'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>CAPITAL-CALL-PLAN.md</span>
        </button>

        <button
          onClick={() => setActiveDoc('python_code')}
          className={`px-3.5 py-2 rounded-xl flex items-center gap-2 transition-all cursor-pointer ${
            activeDoc === 'python_code'
              ? 'bg-[#7048E8] text-white font-bold shadow-xs'
              : 'bg-white hover:bg-gray-50 text-gray-600 border border-gray-200/80'
          }`}
        >
          <Code className="w-3.5 h-3.5" />
          <span>Original Python Logic (app/compliance.py)</span>
        </button>
      </div>

      {/* Document Content */}
      <div className="bg-white border border-gray-100 rounded-2xl p-6 sm:p-8 shadow-xs text-xs text-gray-800 leading-relaxed">
        {activeDoc === 'positioning' && (
          <div className="space-y-6">
            <div className="border-b border-gray-100 pb-4">
              <h1 className="text-xl font-bold text-gray-900">Flowgate — Honest Positioning</h1>
              <p className="text-xs text-[#7048E8] font-semibold mt-1">
                One page. Shipped features mapped to code. Gaps acknowledged. Roadmap separated from what&apos;s built.
              </p>
            </div>

            <div className="space-y-2">
              <h2 className="text-xs uppercase text-gray-400 font-bold tracking-wider">What Flowgate is</h2>
              <p className="text-xs text-gray-700 leading-relaxed">
                Flowgate is the <strong className="text-gray-900">shared pipeline underneath</strong> private-capital operations — document intake, extraction, compliance, and the unified ledger that feeds cap tables and portfolio views. It is the layer that produces clean, compliance-checked data so those layers don&apos;t have to.
              </p>
            </div>

            <div className="space-y-3">
              <h2 className="text-xs uppercase text-gray-400 font-bold tracking-wider">Genuine Differentiators</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-[#F8FAFD] border border-gray-200/80 space-y-1">
                  <div className="text-xs font-bold text-[#7048E8]">
                    Compliance-as-Configuration
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    One gateway, rule sets as data; traditional + Islamic run the identical code path. Carta/Allvue/Arch either skip compliance or do it as per-client custom consulting.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-[#F8FAFD] border border-gray-200/80 space-y-1">
                  <div className="text-xs font-bold text-emerald-700">
                    Islamic + Traditional in One Workflow
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    Same gateway, compliance_mode selects rule sets. Riba prohibition, asset backing, and Fatwa checks natively verified alongside standard commercial loans.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-[#F8FAFD] border border-gray-200/80 space-y-1">
                  <div className="text-xs font-bold text-[#7048E8]">
                    Confidence-Gated Extraction
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    Never guesses. Gate 0.75 for classification, 0.85 for extraction. Below threshold goes to human triage and is never silently accepted.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-[#F8FAFD] border border-gray-200/80 space-y-1">
                  <div className="text-xs font-bold text-emerald-700">
                    Event-Sourced Cap Table
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed">
                    Ownership computed by replaying append-only logs. Overdrafts rejected at write time. Immune to spreadsheet drift.
                  </p>
                </div>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 space-y-1">
              <div className="font-bold text-xs uppercase text-emerald-800">Architecture Guarantee (No Self-Certification)</div>
              <p className="text-xs text-emerald-700 leading-relaxed">
                Enforced at the ORM / gateway level: <code>scholar_approved</code> status can never be written by an automated script. A human reviewer ID is strictly required.
              </p>
            </div>
          </div>
        )}

        {activeDoc === 'captable' && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-gray-900">Cap Table Bridge & Event-Sourcing Roadmap</h2>
            <p className="text-xs text-gray-600 leading-relaxed">
              Documents in Flowgate produce proposed events rather than direct mutations. A named human reviewer must sign off before any change alters diluted ownership.
            </p>
            <div className="bg-[#F8FAFD] p-4 rounded-xl border border-gray-200/80 space-y-3">
              <div>
                <div className="text-xs font-bold text-[#7048E8]">1. Ingestion Stage</div>
                <div className="text-xs text-gray-600">Extraction engine parses subscriber, share quantity, share price, and accredited category.</div>
              </div>
              <div>
                <div className="text-xs font-bold text-[#7048E8]">2. Human Review Gate</div>
                <div className="text-xs text-gray-600">Proposal stays in &apos;proposed&apos; status until verified against investor registry.</div>
              </div>
              <div>
                <div className="text-xs font-bold text-[#7048E8]">3. Deterministic Replay</div>
                <div className="text-xs text-gray-600">Cap table state re-evaluates strictly as <code>positions = replay(events)</code>.</div>
              </div>
            </div>
          </div>
        )}

        {activeDoc === 'capitalcalls' && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold text-gray-900">Capital Call Intake & Overdue Tracking</h2>
            <p className="text-xs text-gray-600 leading-relaxed">
              Drawdown notice extraction extracts LP partner identity, capital owing, payment due dates, and wire routing details.
            </p>
            <div className="bg-[#F8FAFD] p-4 rounded-xl border border-gray-200/80 space-y-2">
              <div className="text-xs font-bold text-emerald-700">Overdue Detection Algorithm:</div>
              <div className="text-xs text-gray-600 leading-relaxed">
                Drawdowns where <code>due_date &lt; current_timestamp</code> and <code>status != &apos;approved&apos;</code> automatically trigger operational alerts and appear under the filtered drawdowns queue.
              </div>
            </div>
          </div>
        )}

        {activeDoc === 'python_code' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-900">app/compliance.py (Cloned Python Repository)</span>
              <span className="text-[11px] text-gray-400 font-mono">Original Backend Logic</span>
            </div>
            <pre className="p-4 rounded-xl bg-[#F8FAFD] border border-gray-200/80 text-[11px] font-mono text-gray-800 overflow-x-auto leading-relaxed">
{`# app/compliance.py
# Compliance-as-configuration: rules are data, not code branches.
# Traditional and Islamic tracks execute through the identical gateway.

class ComplianceGateway:
    """Evaluates an instrument against the ruleset for its compliance_mode."""

    def evaluate(self, db, instrument, document, extracted_fields, attached_fatwa=None):
        ruleset = (
            ISLAMIC_RULES if instrument.compliance_mode == "islamic"
            else TRADITIONAL_RULES
        )
        findings = []
        for rule in ruleset:
            finding = rule(instrument, document, extracted_fields, attached_fatwa)
            if finding is not None:
                findings.append(finding)

        blocking = [f for f in findings if f.severity == "blocking" and f.status == "failed"]
        if blocking:
            outcome = "system_flagged_noncompliant"
        elif instrument.compliance_mode == "islamic":
            outcome = "pending_scholar_review"
        else:
            outcome = "not_applicable"

        return findings, outcome`}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
