import React, { useState } from 'react';
import {
  ComplianceMode,
  PipelineRunResult,
  DocumentType,
  ShariahReviewStatus,
} from '../types';
import {
  SAMPLE_DOCUMENTS,
  classifyDocument,
  extractFields,
  evaluateCompliance,
  generateTraceId,
} from '../services/flowgateEngine';
import {
  FileText,
  Upload,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Sparkles,
  ArrowRight,
  ShieldAlert,
  ShieldCheck,
  FileCheck,
  PlusCircle,
  FileCode,
} from 'lucide-react';

interface PipelineViewProps {
  onPipelineCompleted: (result: PipelineRunResult) => void;
  lastResult: PipelineRunResult | null;
}

export const PipelineView: React.FC<PipelineViewProps> = ({
  onPipelineCompleted,
  lastResult,
}) => {
  const [selectedTemplate, setSelectedTemplate] = useState<string>('Sukuk (al-Ijara)');
  const [docText, setDocText] = useState<string>(SAMPLE_DOCUMENTS['Sukuk (al-Ijara)'].text);
  const [complianceMode, setComplianceMode] = useState<ComplianceMode>('islamic');
  const [activeInputTab, setActiveInputTab] = useState<'paste' | 'upload'>('paste');
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);

  const [isProcessing, setIsProcessing] = useState(false);
  const [activeStep, setActiveStep] = useState<number>(0);
  const [elapsedTime, setElapsedTime] = useState<string>('');
  const [hasAttachedFatwa, setHasAttachedFatwa] = useState(false);

  const handleSelectTemplate = (key: string) => {
    setSelectedTemplate(key);
    const item = SAMPLE_DOCUMENTS[key];
    setDocText(item.text);
    setComplianceMode(item.mode);
    setUploadedFileName(null);
    setHasAttachedFatwa(false);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadedFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        setDocText(content);
      }
    };
    reader.readAsText(file);
  };

  const runPipeline = async (forceWithFatwa = false) => {
    setIsProcessing(true);
    const startTime = performance.now();

    // Step 1: Classification
    setActiveStep(1);
    await new Promise((r) => setTimeout(r, 260));
    const classification = classifyDocument(docText);

    // Step 2: Extraction
    setActiveStep(2);
    await new Promise((r) => setTimeout(r, 340));
    const fields = extractFields(docText, classification.docType);

    // Step 3: Compliance Gateway
    setActiveStep(3);
    await new Promise((r) => setTimeout(r, 400));
    const fatwaEffective = forceWithFatwa || hasAttachedFatwa;
    const { findings, outcome } = evaluateCompliance(
      complianceMode,
      classification.docType,
      fields,
      fatwaEffective
    );

    // Step 4: Ledger append
    setActiveStep(4);
    await new Promise((r) => setTimeout(r, 200));
    const duration = ((performance.now() - startTime) / 1000).toFixed(2);
    setElapsedTime(`${duration}s`);

    const traceId = generateTraceId();
    const docId = 'doc_' + Math.random().toString(36).substring(2, 9);
    const instrumentId = 'inst_' + Math.random().toString(36).substring(2, 9);

    const mapToTxType = (dt: DocumentType) => {
      if (dt === 'sukuk_certificate') return 'sukuk';
      if (dt === 'loan_agreement') return 'loan';
      if (dt === 'limited_partnership_agreement') return 'fund_interest';
      return 'equity';
    };

    const result: PipelineRunResult = {
      instrument: {
        id: instrumentId,
        issuer_name: (fields.find((f) => f.name === 'issuer_name')?.value as string) || 'Global Issuer Corp',
        transaction_type: mapToTxType(classification.docType),
        compliance_mode: complianceMode,
        amount: (fields.find((f) => f.name === 'total_issuance' || f.name === 'principal_amount')?.value as number) || 5000000,
        currency: 'USD',
        shariah_review_status: outcome,
        created_at: new Date().toISOString(),
      },
      document: {
        id: docId,
        instrument_id: instrumentId,
        filename: uploadedFileName || `${selectedTemplate.toLowerCase().replace(/[^a-z0-9]/g, '_')}.txt`,
        document_type: classification.docType,
        confidence: classification.confidence,
        status: classification.confidence >= 0.75 ? 'processed' : 'review_needed',
        extracted_text: docText,
        created_at: new Date().toISOString(),
      },
      extracted_fields: fields,
      compliance_findings: findings,
      compliance_outcome: outcome,
      ledger_entries: [
        {
          id: 'led_' + Math.random().toString(36).substring(2, 9),
          entry_type: 'document_result',
          trace_id: traceId,
          instrument_id: instrumentId,
          title: `Document Processed: ${classification.docType} (confidence ${(classification.confidence * 100).toFixed(0)}%)`,
          details: {
            filename: uploadedFileName || 'sample_input.txt',
            field_count: fields.length,
          },
          timestamp: new Date().toISOString(),
        },
        {
          id: 'led_' + Math.random().toString(36).substring(2, 9),
          entry_type: 'compliance_event',
          trace_id: traceId,
          instrument_id: instrumentId,
          title: `Compliance Decision: ${outcome}`,
          details: {
            mode: complianceMode,
            findings_count: findings.length,
            blocking_failures: findings.filter((f) => f.severity === 'blocking' && f.status === 'failed').length,
          },
          timestamp: new Date().toISOString(),
        },
      ],
    };

    // If subscription agreement, auto-create cap table proposal
    if (classification.docType === 'subscription_agreement') {
      const shareCountField = fields.find((f) => f.name === 'share_count');
      const subscriberField = fields.find((f) => f.name === 'subscriber_name');
      const sharePriceField = fields.find((f) => f.name === 'share_price');
      const issuerField = fields.find((f) => f.name === 'issuer_name');

      result.proposal_created = {
        id: 'prop_' + Math.random().toString(36).substring(2, 9),
        document_id: docId,
        issuer_name: String(issuerField?.value || 'Flowgate Systems Inc.'),
        holder_name: String(subscriberField?.value || 'Apex Horizon Growth Fund LP'),
        share_count: typeof shareCountField?.value === 'number' ? shareCountField.value : 150000,
        share_class: 'Common',
        share_price: 12.5,
        status: 'proposed',
        created_at: new Date().toISOString(),
      };
    }

    setIsProcessing(false);
    onPipelineCompleted(result);
  };

  const handleAttachFatwaAndRecheck = () => {
    setHasAttachedFatwa(true);
    runPipeline(true);
  };

  const formatOutcomeBadge = (outcome: ShariahReviewStatus) => {
    switch (outcome) {
      case 'pending_scholar_review':
        return (
          <span className="px-3 py-1.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-bold text-xs flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" /> PENDING SCHOLAR REVIEW
          </span>
        );
      case 'scholar_approved':
      case 'not_applicable':
        return (
          <span className="px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold text-xs flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> COMPLIANCE PASSED
          </span>
        );
      case 'system_flagged_noncompliant':
      default:
        return (
          <span className="px-3 py-1.5 rounded-full bg-red-50 text-red-700 border border-red-200 font-bold text-xs flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> SYSTEM FLAGGED NONCOMPLIANT
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Template Selector Bar */}
      <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-gray-900 tracking-tight">
              Sample Deal Documents
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Load tested real-world agreements mapped to verification suites
            </p>
          </div>
          <span className="text-xs font-bold text-[#7048E8] bg-[#EBE7FD] px-2.5 py-1 rounded-full border border-purple-200/60">
            Confidence Gated (Classify ≥ 0.75 | Extract ≥ 0.85)
          </span>
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          {Object.keys(SAMPLE_DOCUMENTS).map((key) => {
            const item = SAMPLE_DOCUMENTS[key];
            const isSelected = selectedTemplate === key && !uploadedFileName;
            return (
              <button
                key={key}
                onClick={() => handleSelectTemplate(key)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer ${
                  isSelected
                    ? 'bg-[#7048E8] text-white shadow-xs'
                    : 'bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] border border-gray-200/80'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>{key}</span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold uppercase ${
                    item.mode === 'islamic'
                      ? isSelected ? 'bg-white/20 text-white' : 'bg-emerald-100 text-emerald-800'
                      : isSelected ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-800'
                  }`}
                >
                  {item.mode}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Grid: Input Area + Execution Results */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Col: Document Input & Controls (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
            <div className="flex items-center justify-between border-b border-gray-100 pb-3">
              <div>
                <h3 className="text-sm font-bold text-gray-900">Document Intake</h3>
                <p className="text-xs text-gray-500">Provide agreement text or upload PDF</p>
              </div>
              <div className="flex bg-[#F4F6FC] p-1 rounded-xl border border-gray-200/80">
                <button
                  onClick={() => setActiveInputTab('paste')}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                    activeInputTab === 'paste'
                      ? 'bg-white text-[#7048E8] shadow-xs'
                      : 'text-gray-500 hover:text-gray-900'
                  }`}
                >
                  Paste Text
                </button>
                <button
                  onClick={() => setActiveInputTab('upload')}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
                    activeInputTab === 'upload'
                      ? 'bg-white text-[#7048E8] shadow-xs'
                      : 'text-gray-500 hover:text-gray-900'
                  }`}
                >
                  Upload File
                </button>
              </div>
            </div>

            {activeInputTab === 'paste' ? (
              <div>
                <textarea
                  id="doc-text-input"
                  value={docText}
                  onChange={(e) => setDocText(e.target.value)}
                  rows={10}
                  placeholder="Paste loan agreement, sukuk certificate, safe, or subscription text here..."
                  className="w-full bg-[#F4F6FC] border border-gray-200 rounded-xl p-3 font-mono text-xs text-gray-900 focus:border-[#7048E8] outline-none resize-y"
                />
              </div>
            ) : (
              <div className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center bg-[#F8FAFD]">
                <input
                  type="file"
                  id="file-upload-input"
                  accept=".txt,.md,.pdf,.html"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <label
                  htmlFor="file-upload-input"
                  className="cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white hover:bg-gray-50 text-xs font-bold text-[#7048E8] border border-purple-200 shadow-xs transition-colors"
                >
                  <Upload className="w-4 h-4" />
                  <span>Choose file (.txt, .md, .pdf)</span>
                </label>
                <p className="text-xs text-gray-500 mt-3">
                  {uploadedFileName ? (
                    <span className="text-emerald-600 font-semibold">Loaded: {uploadedFileName}</span>
                  ) : (
                    'Supports plain text, Markdown, legal drafts, or term sheets'
                  )}
                </p>
              </div>
            )}

            {/* Compliance Mode Selector */}
            <div className="pt-2 border-t border-gray-100">
              <label className="block text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">
                COMPLIANCE GATEWAY TRACK
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setComplianceMode('traditional')}
                  className={`p-3 rounded-xl text-xs border text-left transition-all cursor-pointer ${
                    complianceMode === 'traditional'
                      ? 'bg-[#EBF0FD] border-[#2342E3] text-gray-900 shadow-xs'
                      : 'bg-[#F4F6FC] border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  <div className="font-bold mb-0.5 text-gray-900">Traditional Track</div>
                  <div className="text-[10px] text-gray-500">KYC/AML, interest bounds, governing law</div>
                </button>

                <button
                  type="button"
                  onClick={() => setComplianceMode('islamic')}
                  className={`p-3 rounded-xl text-xs border text-left transition-all cursor-pointer ${
                    complianceMode === 'islamic'
                      ? 'bg-emerald-50 border-emerald-600 text-gray-900 shadow-xs'
                      : 'bg-[#F4F6FC] border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  <div className="font-bold mb-0.5 text-gray-900">Islamic Track</div>
                  <div className="text-[10px] text-gray-500">Riba prohibition, asset backing, Fatwa check</div>
                </button>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="pt-1">
              <button
                id="process-document-btn"
                onClick={() => runPipeline(false)}
                disabled={isProcessing}
                className="w-full py-3 px-4 rounded-xl bg-[#7048E8] hover:bg-[#5C38D1] text-white text-xs font-bold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer shadow-xs"
              >
                {isProcessing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Evaluating Pipeline...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Run Pipeline Assessment</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Quick Info Box */}
          <div className="bg-white rounded-2xl p-4 border border-gray-100 shadow-xs text-xs text-gray-600 space-y-1.5">
            <div className="text-gray-900 font-bold flex items-center gap-2">
              <FileCheck className="w-4 h-4 text-[#7048E8]" />
              <span>Architectural Guarantee</span>
            </div>
            <p className="text-[11px] leading-relaxed text-gray-500">
              No self-certification: Scholar approval can never be automatically minted by code.
              Uncertified Islamic debt is blocked or held in review until human endorsement is logged in the audit ledger.
            </p>
          </div>
        </div>

        {/* Right Col: Interactive Pipeline Stages & Findings (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          {/* Progress Timeline Stepper */}
          <div className="bg-white rounded-2xl p-4 sm:p-5 shadow-xs border border-gray-100">
            <div className="flex items-center justify-between mb-3 text-xs">
              <span className="font-bold text-gray-700 uppercase tracking-wider text-[11px]">
                PIPELINE EXECUTION STAGES
              </span>
              {elapsedTime && (
                <span className="text-xs font-mono font-bold text-[#7048E8] bg-[#EBE7FD] px-2 py-0.5 rounded-full">
                  {elapsedTime} elapsed
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                { step: 1, name: '1. Classify', desc: 'Lexicon scoring' },
                { step: 2, name: '2. Extract', desc: 'Entity parsing' },
                { step: 3, name: '3. Compliance', desc: 'Rule evaluation' },
                { step: 4, name: '4. Ledger', desc: 'Append-only trace' },
              ].map((s) => {
                const isComplete = !isProcessing && lastResult ? true : activeStep > s.step;
                const isCurrent = isProcessing && activeStep === s.step;
                return (
                  <div
                    key={s.step}
                    className={`p-2.5 rounded-xl border text-center transition-all ${
                      isComplete
                        ? 'bg-emerald-50/70 border-emerald-200 text-emerald-800'
                        : isCurrent
                        ? 'bg-[#EBE7FD] border-purple-300 text-[#7048E8] animate-pulse'
                        : 'bg-[#F4F6FC] border-gray-200 text-gray-400'
                    }`}
                  >
                    <div className="text-xs font-bold">{s.name}</div>
                    <div className="text-[10px] opacity-80">{s.desc}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Results Display */}
          {lastResult ? (
            <div className="space-y-4">
              {/* Outcome Header Banner */}
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-bold text-gray-400 uppercase mb-1">
                    DOCUMENT EVALUATION OUTCOME
                  </div>
                  <div className="text-lg font-bold text-gray-900">
                    {lastResult.instrument.issuer_name}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    Type: <span className="font-semibold text-gray-800 capitalize">{lastResult.document.document_type.replace('_', ' ')}</span> &bull;{' '}
                    Confidence: <span className="font-bold text-emerald-600">{(lastResult.document.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>

                <div>{formatOutcomeBadge(lastResult.compliance_outcome)}</div>
              </div>

              {/* Islamic Fatwa Fix Flow */}
              {lastResult.compliance_outcome === 'system_flagged_noncompliant' &&
                complianceMode === 'islamic' && (
                  <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="space-y-1">
                      <div className="text-xs font-bold text-amber-800 flex items-center gap-1.5">
                        <ShieldAlert className="w-4 h-4 text-amber-600" />
                        <span>Missing Fatwa Certification Evidence</span>
                      </div>
                      <p className="text-[11px] text-amber-700">
                        Rule <code className="font-mono font-bold">SHAR_FATWA_MISSING</code> blocked clearance. Attach verified Shariah Supervisory Board Fatwa to proceed.
                      </p>
                    </div>
                    <button
                      id="attach-fatwa-btn"
                      onClick={handleAttachFatwaAndRecheck}
                      className="px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold whitespace-nowrap transition-colors cursor-pointer shadow-xs"
                    >
                      Attach Fatwa & Re-evaluate
                    </button>
                  </div>
                )}

              {/* Cap Table Proposal Generated Notification */}
              {lastResult.proposal_created && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="text-xs font-bold text-emerald-800 flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      <span>Cap Table Proposal Prepared</span>
                    </div>
                    <p className="text-[11px] text-emerald-700">
                      Subscription agreement extracted {lastResult.proposal_created.share_count.toLocaleString()} Common shares for{' '}
                      <strong>{lastResult.proposal_created.holder_name}</strong>. Ready in Cap Table Proposals tab for human sign-off.
                    </p>
                  </div>
                </div>
              )}

              {/* Extracted Fields Box */}
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 space-y-3">
                <div className="flex items-center justify-between border-b border-gray-100 pb-2.5">
                  <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wide flex items-center gap-1.5">
                    <FileCode className="w-4 h-4 text-[#7048E8]" />
                    <span>Structured Extracted Fields</span>
                  </h4>
                  <span className="text-[11px] text-gray-500 font-medium">
                    {lastResult.extracted_fields.length} entities parsed
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {lastResult.extracted_fields.map((f, i) => (
                    <div
                      key={i}
                      className="p-3 rounded-xl bg-[#F8FAFD] border border-gray-200/70 text-xs"
                    >
                      <div className="text-[10px] text-gray-400 font-bold uppercase">
                        {f.name.replace(/_/g, ' ')}
                      </div>
                      <div className="text-gray-900 font-bold mt-0.5 truncate">
                        {String(f.value)}
                      </div>
                      <div className="text-[10px] text-[#7048E8] font-semibold mt-1">
                        Confidence: {(f.confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Compliance Rule Findings Checklist */}
              <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 space-y-3">
                <div className="flex items-center justify-between border-b border-gray-100 pb-2.5">
                  <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wide flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-[#20C997]" />
                    <span>Compliance Findings & Audit Rules</span>
                  </h4>
                  <span className="text-[11px] text-gray-500 font-medium">
                    {lastResult.compliance_findings.length} rule checks
                  </span>
                </div>

                <div className="space-y-2">
                  {lastResult.compliance_findings.map((finding) => (
                    <div
                      key={finding.rule_id}
                      className={`p-3.5 rounded-xl border text-xs transition-all ${
                        finding.status === 'passed'
                          ? 'bg-white border-emerald-100 shadow-2xs'
                          : 'bg-amber-50/50 border-amber-200'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          {finding.status === 'passed' ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                          ) : (
                            <XCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                          )}
                          <span className="font-bold text-gray-900">{finding.name}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 border border-gray-200">
                            {finding.rule_id}
                          </span>
                        </div>
                        <span
                          className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                            finding.severity === 'blocking'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {finding.severity}
                        </span>
                      </div>
                      <p className="text-[11px] text-gray-600 pl-6">{finding.summary}</p>
                      {finding.remedy && (
                        <p className="text-[11px] text-amber-800 pl-6 mt-1 bg-amber-100/50 p-2 rounded-lg border border-amber-200">
                          <strong>Remedy:</strong> {finding.remedy}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white border border-dashed border-gray-200 rounded-2xl p-12 text-center shadow-xs">
              <div className="w-12 h-12 rounded-2xl bg-[#EBE7FD] text-[#7048E8] flex items-center justify-center mx-auto mb-3">
                <FileText className="w-6 h-6" />
              </div>
              <h4 className="text-base font-bold text-gray-900 mb-1">
                No Document Processed Yet
              </h4>
              <p className="text-xs text-gray-500 max-w-md mx-auto">
                Select one of the sample deal agreements on the left, or paste your own document and click &quot;Run Pipeline Assessment&quot;.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
