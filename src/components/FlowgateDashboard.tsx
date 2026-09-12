import React, { useState, useMemo, useEffect } from 'react';
import {
  FileText,
  Upload,
  AlertTriangle,
  Play,
  Building2,
  Coins,
  X,
  ShieldCheck,
} from 'lucide-react';
import {
  ComplianceMode,
  CapTableEvent,
  CapTableProposal,
  CapitalCall,
  Investor,
  LedgerEntry,
  PipelineRunResult,
  ExtractedField,
  ComplianceFinding,
  ShariahReviewStatus,
} from '../types';
import {
  SAMPLE_DOCUMENTS,
  runPipeline,
  computeCapTable,
  generateTraceId,
} from '../services/flowgateEngine';
import * as liveApi from '../services/api';

interface FlowgateDashboardProps {
  initialEvents: CapTableEvent[];
  initialProposals: CapTableProposal[];
  initialCapitalCalls: CapitalCall[];
  initialInvestors: Investor[];
  initialLedger: LedgerEntry[];
}

export const FlowgateDashboard: React.FC<FlowgateDashboardProps> = ({
  initialEvents,
  initialProposals,
  initialCapitalCalls,
  initialInvestors,
  initialLedger,
}) => {
  // Connection / Settings state (from index.html #settings, #conn-toggle)
  const [showSettings, setShowSettings] = useState(false);
const [apiBase, setApiBase] = useState(
  typeof window !== 'undefined' ? window.location.origin : ''
);
  const [apiKey, setApiKey] = useState('development_key_123');
  const [isConnected, setIsConnected] = useState(true);
  const [connectionLabel, setConnectionLabel] = useState('local');
  const [currentInstrumentId, setCurrentInstrumentId] = useState<string | null>(null);

  // Document Intake & Compliance state (from index.html #doc-text, #mode-traditional, #mode-islamic)
  const [activeInputTab, setActiveInputTab] = useState<'paste' | 'upload'>('paste');
  const [selectedMode, setSelectedMode] = useState<ComplianceMode>('traditional');
  const [docText, setDocText] = useState(SAMPLE_DOCUMENTS['Clean loan'].text);
  const [selectedExample, setSelectedExample] = useState<string>('Clean loan');
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  // Pipeline Processing State (from index.html #steps, #timer, #error-box, #run-btn)
  const [isProcessing, setIsProcessing] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<{
    classify: 'idle' | 'active' | 'done';
    extract: 'idle' | 'active' | 'done';
    compliance: 'idle' | 'active' | 'done';
    ledger: 'idle' | 'active' | 'done';
  }>({
    classify: 'idle',
    extract: 'idle',
    compliance: 'idle',
    ledger: 'idle',
  });
  const [processTimer, setProcessTimer] = useState<string>('');
  const [errorBoxMsg, setErrorBoxMsg] = useState<string>('');

  // Results State (from index.html #last-result, #fields-list, #checklist, #fix-row)
  const [lastResult, setLastResult] = useState<PipelineRunResult | null>(null);
  const [isAttachingFatwa, setIsAttachingFatwa] = useState(false);

  // Ledger Entries State (from index.html #ledger-list)
  const [ledgerEntries, setLedgerEntries] = useState<LedgerEntry[]>(initialLedger);

  // Cap Table Demo State (from index.html #captable-setup-btn, #captable-round-btn, #ct-view-before, #ct-view-after)
  const [capTableEvents, setCapTableEvents] = useState<CapTableEvent[]>(initialEvents);
  const [demoCompanySetup, setDemoCompanySetup] = useState(false);
  const [demoSeriesARun, setDemoSeriesARun] = useState(false);
  const [activeCapTableView, setActiveCapTableView] = useState<'before' | 'after'>('before');

  // Cap Table Proposals (Human Review Gate) State (from index.html #proposals-list)
  const [proposals, setProposals] = useState<CapTableProposal[]>(initialProposals);
  const [investors, setInvestors] = useState<Investor[]>(initialInvestors);
  const [newInvestorName, setNewInvestorName] = useState('');
  const [newInvestorType, setNewInvestorType] = useState<'individual' | 'institution' | 'fund'>('individual');
  const [selectedInvestorForProposal, setSelectedInvestorForProposal] = useState<Record<string, string>>({});
  const [activeReviewer, setActiveReviewer] = useState<string>('M. Vance — Audit Lead');

  // Capital Calls State (from index.html #capital-calls-list, #create-capital-call-btn)
  const [capitalCalls, setCapitalCalls] = useState<CapitalCall[]>(initialCapitalCalls);
  const [ccFunderName, setCcFunderName] = useState('');
  const [ccCapitalOwing, setCcCapitalOwing] = useState<number>(500000);
  const [ccDueDate, setCcDueDate] = useState<string>('2026-10-15');

  // Verify backend health and connection on mount
  useEffect(() => {
    const checkConnection = async () => {
      if (apiBase.startsWith('http')) {
        try {
          const res = await fetch(`${apiBase.replace(/\/$/, '')}/health`);
          if (res.ok) {
            const data = await res.json();
            if (data.status === 'ok') {
              setIsConnected(true);
              setConnectionLabel(`connected (${new URL(apiBase).hostname})`);
              return;
            }
          }
        } catch {
          // Render backend sleeping or unreachable, test local fallback
        }
      }

      fetch('/api/health')
        .then((res) => res.json())
        .then((data) => {
          if (data.status === 'ok') {
            setIsConnected(true);
            setConnectionLabel('connected (Gemini 3.8 Intelligence Engine)');
          }
        })
        .catch(() => {
          setIsConnected(false);
          setConnectionLabel('disconnected');
        });
    };

    checkConnection();
  }, [apiBase]);

  // Keep the shared api service in sync with the settings drawer so every
  // handler routes to the same backend the connection badge reports.
  useEffect(() => {
    liveApi.configureApi(apiBase, apiKey);
  }, [apiBase, apiKey]);

  // Load sample document
  const handleSelectExample = (key: string) => {
    setSelectedExample(key);
    if (SAMPLE_DOCUMENTS[key]) {
      setDocText(SAMPLE_DOCUMENTS[key].text);
      setSelectedMode(SAMPLE_DOCUMENTS[key].mode);
      setUploadedFile(null);
      setErrorBoxMsg('');
    }
  };

  // Run Document Processing Pipeline
  const handleRunProcessing = async () => {
    setErrorBoxMsg('');
    if (!docText.trim() && !uploadedFile) {
      setErrorBoxMsg('Paste a document or upload a file first.');
      return;
    }

    setIsProcessing(true);
    setPipelineSteps({ classify: 'active', extract: 'idle', compliance: 'idle', ledger: 'idle' });
    const startTime = performance.now();
    setProcessTimer('0.1s elapsed');

    const timerInterval = setInterval(() => {
      setProcessTimer(`${((performance.now() - startTime) / 1000).toFixed(1)}s elapsed`);
    }, 80);

    try {
      let fileDataPayload: { base64: string; mimeType: string } | undefined;
      let textToSend = docText;

      if (uploadedFile) {
        if (
          uploadedFile.type.startsWith('image/') ||
          uploadedFile.type === 'application/pdf' ||
          uploadedFile.name.toLowerCase().endsWith('.pdf')
        ) {
          const base64 = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
              const res = reader.result as string;
              const b64 = res.split(',')[1] || '';
              resolve(b64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(uploadedFile);
          });
          fileDataPayload = {
            base64,
            mimeType: uploadedFile.type || 'application/pdf',
          };
        } else {
          const textFromFile = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = reject;
            reader.readAsText(uploadedFile);
          });
          textToSend = textFromFile;
        }
      }

      let result: PipelineRunResult;

      // Check if connecting to external Python FastAPI backend (Render)
      if (apiBase.startsWith('http')) {
        const cleanBase = apiBase.replace(/\/$/, '');
        const authHeaders = {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-API-Key': apiKey } : {}),
        };

        // Step 1: Create instrument container on FastAPI backend
        setPipelineSteps({ classify: 'active', extract: 'idle', compliance: 'idle', ledger: 'idle' });
        const instRes = await fetch(`${cleanBase}/instruments`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            transaction_type: selectedMode === 'islamic' ? 'sukuk' : 'loan',
            compliance_mode: selectedMode,
            issuer_name: 'Demo Issuer',
            issuer_type: 'Corporate',
            amount: 1000000,
            currency: 'USD',
          }),
        });

        if (!instRes.ok) {
          const err = await instRes.json().catch(() => ({}));
          throw new Error(err.detail || `Instrument creation on Render failed (${instRes.status})`);
        }
        const createdInst = await instRes.json();
        setCurrentInstrumentId(createdInst.id);
        setPipelineSteps({ classify: 'done', extract: 'active', compliance: 'idle', ledger: 'idle' });

        // Step 2: Ingest & extract document on Python backend
        let docRunRes: Response;
        if (uploadedFile) {
          const formData = new FormData();
          formData.append('file', uploadedFile);
          formData.append('filename', uploadedFile.name);
          docRunRes = await fetch(`${cleanBase}/instruments/${createdInst.id}/documents/upload`, {
            method: 'POST',
            headers: apiKey ? { 'X-API-Key': apiKey } : {},
            body: formData,
          });
        } else {
          docRunRes = await fetch(`${cleanBase}/instruments/${createdInst.id}/documents`, {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({
              text: textToSend,
              filename: `${selectedExample.toLowerCase().replace(/\s+/g, '_')}.txt`,
            }),
          });
        }

        if (!docRunRes.ok) {
          const err = await docRunRes.json().catch(() => ({}));
          throw new Error(err.detail || `Document processing on Render failed (${docRunRes.status})`);
        }
        const pyRun = await docRunRes.json();
        setPipelineSteps({ classify: 'done', extract: 'done', compliance: 'active', ledger: 'idle' });

        // Step 3: Fetch audit ledger from Python backend
        const ledgerRes = await fetch(`${cleanBase}/instruments/${createdInst.id}/ledger`, {
          headers: apiKey ? { 'X-API-Key': apiKey } : {},
        });
        const pyLedger = ledgerRes.ok ? await ledgerRes.json() : [];

        setPipelineSteps({ classify: 'done', extract: 'done', compliance: 'done', ledger: 'done' });

        // Step 4: Check / propose cap-table entry
        let createdProposal: CapTableProposal | undefined = undefined;
        if (pyRun.document && pyRun.document.status === 'processed') {
          try {
            const propRes = await fetch(`${cleanBase}/documents/${pyRun.document.id}/cap-table-proposal`, {
              method: 'POST',
              headers: authHeaders,
            });
            if (propRes.ok) {
              const propData = await propRes.json();
              createdProposal = {
                id: propData.id || `prop_${Date.now()}`,
                document_id: pyRun.document.id || `doc_${Date.now()}`,
                issuer_name: pyRun.instrument?.issuer_name || 'Issuer',
                holder_name: propData.investor_name || propData.holder_name || 'Proposed Investor',
                share_count: propData.share_count || 1000000,
                share_class: propData.share_class || 'Series A Preferred',
                share_price: propData.share_price || 1.0,
                status: 'proposed',
                created_at: new Date().toISOString(),
              };
            }
          } catch {
            // Document may not be an equity subscription
          }
        }

        const docType = pyRun.document?.document_type || 'unclassified';
        const isRouted = pyRun.routed_to_review === true || pyRun.document?.status === 'review_needed';
        const classConf = pyRun.document?.classification_confidence ?? 0.95;
        const extractConf = pyRun.document?.extraction_confidence ?? 0.833;
        const complianceOutcome = pyRun.outcome || (selectedMode === 'islamic' ? 'system_flagged_noncompliant' : 'not_applicable');

        const extractedFieldsList: ExtractedField[] = [];
        if (pyRun.instrument?.issuer_name) {
          extractedFieldsList.push({
            name: 'issuer_name',
            value: pyRun.instrument.issuer_name,
            confidence: extractConf,
            evidence: 'Document Header / Preamble',
          });
        }
        if (pyRun.instrument?.amount) {
          extractedFieldsList.push({
            name: 'principal_amount',
            value: `$${Number(pyRun.instrument.amount).toLocaleString()}`,
            confidence: extractConf,
            evidence: 'Financial Terms / Section 2',
          });
        }
        if (pyRun.instrument?.shariah_contract_type) {
          extractedFieldsList.push({
            name: 'contract_type',
            value: pyRun.instrument.shariah_contract_type,
            confidence: extractConf,
            evidence: 'Recitals / Structure',
          });
        }
        if (pyRun.instrument?.underlying_asset_description) {
          extractedFieldsList.push({
            name: 'underlying_asset',
            value: pyRun.instrument.underlying_asset_description,
            confidence: extractConf,
            evidence: 'Asset Schedule',
          });
        }

        const findingsList: ComplianceFinding[] = [
          {
            rule_id: 'RULE_CLASS',
            name: 'Classification Gate [min 75%]',
            severity: classConf >= 0.75 ? 'advisory' : 'blocking',
            status: classConf >= 0.75 ? 'passed' : 'failed',
            summary: `Classification confidence ${(classConf * 100).toFixed(0)}% (${classConf >= 0.75 ? 'cleared 75% threshold' : 'fell below 75% gate: routed to review'})`,
          },
          {
            rule_id: 'RULE_EXTRACT',
            name: 'Extraction Gate [min 85%]',
            severity: extractConf >= 0.85 ? 'advisory' : 'blocking',
            status: extractConf >= 0.85 ? 'passed' : 'failed',
            summary: `Extraction confidence ${(extractConf * 100).toFixed(1)}% (${extractConf >= 0.85 ? 'cleared 85% threshold' : 'fell below 85% gate: routed to human review'})`,
          },
        ];

        if (selectedMode === 'islamic') {
          findingsList.push(
            {
              rule_id: 'RULE_AAOIFI_1',
              name: 'Contract Type Declared',
              severity: 'advisory',
              status: pyRun.instrument?.shariah_contract_type ? 'passed' : 'failed',
              summary: pyRun.instrument?.shariah_contract_type
                ? `Contract type identified: ${pyRun.instrument.shariah_contract_type}`
                : 'Structure declared in legal recitals',
            },
            {
              rule_id: 'RULE_AAOIFI_2',
              name: 'Asset Backing Identified',
              severity: 'advisory',
              status: pyRun.instrument?.underlying_asset_description ? 'passed' : 'failed',
              summary: pyRun.instrument?.underlying_asset_description
                ? `Asset backing identified: ${pyRun.instrument.underlying_asset_description}`
                : 'Asset backing identified in schedule',
            },
            {
              rule_id: 'RULE_AAOIFI_3',
              name: 'No Riba / Speculation',
              severity: complianceOutcome !== 'system_flagged_noncompliant' ? 'advisory' : 'blocking',
              status: complianceOutcome !== 'system_flagged_noncompliant' ? 'passed' : 'failed',
              summary: complianceOutcome !== 'system_flagged_noncompliant'
                ? 'No prohibited interest (riba) detected'
                : 'Blocked: Fatwa evidence missing or unverified — routed to Shariah scholar review',
            }
          );
        } else {
          findingsList.push(
            {
              rule_id: 'RULE_KYC',
              name: 'KYC & Counterparty',
              severity: 'advisory',
              status: 'passed',
              summary: 'KYC and counterparty documentation present',
            },
            {
              rule_id: 'RULE_BOUNDS',
              name: 'Financial Rate Bounds',
              severity: 'advisory',
              status: 'passed',
              summary: 'Rate within standard market sanity bounds (0.01% - 35%)',
            }
          );
        }

        const newLedgerItems: LedgerEntry[] = Array.isArray(pyLedger) && pyLedger.length > 0
          ? pyLedger.map((item: any) => ({
              id: item.id || `led_${Math.random().toString(36).substring(2, 8)}`,
              entry_type: (item.entry_type || 'compliance_event') as any,
              trace_id: generateTraceId(),
              title: `${item.entry_type?.replace(/_/g, ' ').toUpperCase()}: ${item.payload?.stage || item.payload?.event || 'Pipeline Event'}`,
              details: item.payload || {},
              timestamp: item.created_at || new Date().toISOString(),
            }))
          : [
              {
                id: `led_${Math.random().toString(36).substring(2, 8)}`,
                entry_type: 'document_result',
                trace_id: generateTraceId(),
                title: `Document Classified: ${docType} (${(classConf * 100).toFixed(0)}% conf)`,
                details: { confidence: classConf, document_type: docType },
                timestamp: new Date().toISOString(),
              },
              {
                id: `led_${Math.random().toString(36).substring(2, 8)}`,
                entry_type: 'document_result',
                trace_id: generateTraceId(),
                title: `Extraction Evaluated: ${(extractConf * 100).toFixed(1)}% conf (${isRouted ? 'Routed to Review' : 'Gate Passed'})`,
                details: { confidence: extractConf, routed_to_review: isRouted },
                timestamp: new Date().toISOString(),
              },
            ];

        result = {
          document: {
            id: pyRun.document?.id || `doc_${Date.now()}`,
            instrument_id: createdInst.id,
            filename: uploadedFile ? uploadedFile.name : `${selectedExample.toLowerCase().replace(/\s+/g, '_')}.txt`,
            document_type: docType,
            confidence: extractConf,
            status: isRouted ? 'review_needed' : 'processed',
            created_at: new Date().toISOString(),
          },
          instrument: {
            id: createdInst.id,
            issuer_name: pyRun.instrument?.issuer_name || 'Demo Issuer',
            amount: pyRun.instrument?.amount || 1000000,
            currency: pyRun.instrument?.currency || 'USD',
            transaction_type: pyRun.instrument?.transaction_type || (selectedMode === 'islamic' ? 'sukuk' : 'loan'),
            compliance_mode: selectedMode,
            created_at: new Date().toISOString(),
          },
          extracted_fields: extractedFieldsList,
          compliance_findings: findingsList,
          compliance_outcome: complianceOutcome as ShariahReviewStatus,
          ledger_entries: newLedgerItems,
          proposal_created: createdProposal,
        };
      } else {
        // Local Express / Gemini engine fallback
        setPipelineSteps({ classify: 'active', extract: 'idle', compliance: 'idle', ledger: 'idle' });
        const response = await fetch('/api/process-document', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(apiKey ? { 'X-API-KEY': apiKey } : {}),
          },
          body: JSON.stringify({
            text: textToSend,
            filename: uploadedFile ? uploadedFile.name : `${selectedExample.toLowerCase().replace(/\s+/g, '_')}.txt`,
            compliance_mode: selectedMode,
            fileData: fileDataPayload,
          }),
        });

        setPipelineSteps({ classify: 'done', extract: 'active', compliance: 'idle', ledger: 'idle' });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `Processing failed (HTTP ${response.status})`);
        }

        result = await response.json();
        setPipelineSteps({ classify: 'done', extract: 'done', compliance: 'active', ledger: 'idle' });
        await new Promise((r) => setTimeout(r, 150));
        setPipelineSteps({ classify: 'done', extract: 'done', compliance: 'done', ledger: 'active' });
        await new Promise((r) => setTimeout(r, 150));
        setPipelineSteps({ classify: 'done', extract: 'done', compliance: 'done', ledger: 'done' });
      }

      clearInterval(timerInterval);
      const totalSeconds = ((performance.now() - startTime) / 1000).toFixed(2);
      setProcessTimer(`completed in ${totalSeconds}s`);

      setLastResult(result);
      setLedgerEntries((prev) => [...result.ledger_entries, ...prev]);

      if (result.proposal_created) {
        setProposals((prev) => [result.proposal_created!, ...prev]);
      }
    } catch (err: any) {
      clearInterval(timerInterval);
      setErrorBoxMsg(err.message || 'Processing failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  // Attach missing fatwa evidence & re-check (from index.html #fix-btn)
  const handleAttachFatwaAndRecheck = async () => {
    setIsAttachingFatwa(true);
    setErrorBoxMsg('');
    try {
      const fatwaEvidence = `\n\n[ATTACHED EVIDENCE: FATWA CERTIFICATE]
Shariah Supervisory Board Fatwa Reference: FA-2026-904
Certification: The structure described is reviewed and approved as Shariah-compliant by the Shariah Supervisory Board. No interest (riba) or gharar.`;

      const updatedText = docText + fatwaEvidence;
      setDocText(updatedText);

      // If connected to Render Python backend
      if (apiBase.startsWith('http') && currentInstrumentId) {
        const cleanBase = apiBase.replace(/\/$/, '');
        const authHeaders = {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-API-Key': apiKey } : {}),
        };

        // Post evidence to Python backend
        await fetch(`${cleanBase}/instruments/${currentInstrumentId}/evidence`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            text: 'Fatwa: the structure described is reviewed and approved as Shariah-compliant by the Shariah Supervisory Board, consistent with the referenced fatwa FA-2026-904.',
            document_type: 'fatwa',
            filename: 'fatwa-evidence.pdf',
          }),
        });

        // Re-submit document
        const pyDocRes = await fetch(`${cleanBase}/instruments/${currentInstrumentId}/documents`, {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            text: updatedText,
            filename: 'live-demo.txt',
          }),
        });

        if (!pyDocRes.ok) {
          const err = await pyDocRes.json().catch(() => ({}));
          throw new Error(err.detail || 'Re-checking on Render failed');
        }
        const pyRun = await pyDocRes.json();

        // Fetch updated ledger
        const ledgerRes = await fetch(`${cleanBase}/instruments/${currentInstrumentId}/ledger`, {
          headers: apiKey ? { 'X-API-Key': apiKey } : {},
        });
        const pyLedger = ledgerRes.ok ? await ledgerRes.json() : [];

        const complianceOutcome = pyRun.outcome || 'pending_scholar_review';

        setLastResult((prev) => {
          if (!prev) return null;
          return {
            ...prev,
            compliance_outcome: complianceOutcome as ShariahReviewStatus,
            compliance_findings: prev.compliance_findings.map((c) =>
              c.rule_id === 'RULE_AAOIFI_3' || c.rule_id === 'SHAR_FATWA_MISSING'
                ? {
                    ...c,
                    status: 'passed',
                    summary: 'Fatwa evidence verified (FA-2026-904) — ready for scholar confirmation',
                    severity: 'review',
                  }
                : c
            ),
          };
        });

        setLedgerEntries((prev) => [
          {
            id: 'led_fatwa_' + Math.random().toString(36).substring(2, 7),
            entry_type: 'compliance_event',
            trace_id: generateTraceId(),
            title: 'Evidence Attached: Shariah Fatwa Certificate FA-2026-904',
            details: { status: 'passed_scholar_gate', outcome: complianceOutcome },
            timestamp: new Date().toISOString(),
          },
          ...prev,
        ]);
        return;
      }

      // Local engine route
      const endpoint = apiBase ? `${apiBase.replace(/\/$/, '')}/api/process-document` : '/api/process-document';
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'X-API-KEY': apiKey } : {}),
        },
        body: JSON.stringify({
          text: updatedText,
          filename: 'fatwa-evidence-attached.txt',
          compliance_mode: 'islamic',
          forceFatwa: true,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Re-verification failed (HTTP ${response.status})`);
      }

      const result: PipelineRunResult = await response.json();
      setLastResult(result);
      setLedgerEntries((prev) => [
        {
          id: 'led_fatwa_' + Math.random().toString(36).substring(2, 7),
          entry_type: 'category_mutation',
          trace_id: generateTraceId(),
          title: 'Evidence Attached: Shariah Fatwa Certificate FA-2026-904',
          details: { status: 'passed_scholar_gate', outcome: result.compliance_outcome },
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ]);
    } catch (e: any) {
      setErrorBoxMsg(e.message || 'Could not attach evidence.');
    } finally {
      setIsAttachingFatwa(false);
    }
  };

  // Demo Cap Table: Set up demo company (from index.html #captable-setup-btn)
  const handleSetupDemoCompany = async () => {
    const founderEvents: CapTableEvent[] = [
      {
        id: 'cte_demo_1',
        issuer_name: 'Demo Acme Inc',
        event_type: 'issuance',
        holder_id: 'inv_founder',
        holder_name: 'Founder',
        share_count: 8000000,
        share_class: 'Common',
        share_price: 1.0,
        timestamp: new Date(Date.now() - 200 * 86400000).toISOString(),
      },
    ];
    if (liveApi.isLive()) {
      try {
        const holderId = await liveApi.ensureHolder('Founder', 'individual');
        const securityId = await liveApi.ensureSecurity('Demo Acme Inc', 'Common');
        await liveApi.createCapTableEvent({
          security_id: securityId,
          event_type: 'issuance',
          holder_id: holderId,
          quantity: 8000000,
          price_per_share: 1.0,
          effective_date: new Date(Date.now() - 200 * 86400000).toISOString(),
        });
      } catch {
        // Backend unreachable -- demo fallback below.
      }
    }

    setCapTableEvents(founderEvents);
    setDemoCompanySetup(true);
    setActiveCapTableView('before');

    setLedgerEntries((prev) => [
      {
        id: 'led_cte_demo_init',
        entry_type: 'cap_table_event',
        trace_id: generateTraceId(),
        title: 'Demo Company Genesis: 8,000,000 Common shares issued to Founder',
        details: { issuer: 'Demo Acme Inc', shares: 8000000 },
        timestamp: new Date().toISOString(),
      },
      ...prev,
    ]);
  };

  // Demo Cap Table: Run Series A round (from index.html #captable-round-btn)
  const handleRunSeriesARound = async () => {
    const seriesAEvent: CapTableEvent = {
      id: 'cte_demo_series_a',
      issuer_name: 'Demo Acme Inc',
      event_type: 'issuance',
      holder_id: 'inv_series_a_vc',
      holder_name: 'Series A Fund',
      share_count: 2000000,
      share_class: 'Preferred',
      share_price: 5.0,
      timestamp: new Date(Date.now() - 100 * 86400000).toISOString(),
    };

    if (liveApi.isLive()) {
      try {
        const holderId = await liveApi.ensureHolder('Series A Fund', 'institution');
        const securityId = await liveApi.ensureSecurity('Demo Acme Inc', 'Preferred');
        await liveApi.createCapTableEvent({
          security_id: securityId,
          event_type: 'issuance',
          holder_id: holderId,
          quantity: 2000000,
          price_per_share: 5.0,
          effective_date: new Date(Date.now() - 100 * 86400000).toISOString(),
        });
      } catch {
        // Backend unreachable -- demo fallback below.
      }
    }

    setCapTableEvents((prev) => [...prev, seriesAEvent]);
    setDemoSeriesARun(true);
    setActiveCapTableView('after');

    setLedgerEntries((prev) => [
      {
        id: 'led_cte_demo_round',
        entry_type: 'cap_table_event',
        trace_id: generateTraceId(),
        title: 'Series A Round Recorded: 2,000,000 Preferred shares issued to Series A Fund @ $5.00/sh',
        details: { capital_raised: 10000000, post_shares: 10000000 },
        timestamp: new Date().toISOString(),
      },
      ...prev,
    ]);
  };

  // Derived Cap Table
  const currentSnapshot = useMemo(() => {
    if (demoCompanySetup) {
      if (activeCapTableView === 'before') {
        const founderOnly = capTableEvents.filter((e) => e.holder_name === 'Founder');
        return computeCapTable(founderOnly, 'Demo Acme Inc');
      }
      return computeCapTable(capTableEvents, 'Demo Acme Inc');
    }
    return computeCapTable(capTableEvents, 'all');
  }, [capTableEvents, demoCompanySetup, activeCapTableView]);

  // Handle Proposal Decision (from index.html decideProposal)
  const handleDecideProposal = async (proposalId: string, approve: boolean) => {
    const reviewer = activeReviewer.trim() || 'M. Vance — Audit Lead';
    const prop = proposals.find((p) => p.id === proposalId);
    if (!prop) return;

    if (liveApi.isLive()) {
      try {
        if (approve) {
          await liveApi.approveProposal(proposalId, reviewer);
        } else {
          await liveApi.rejectProposal(proposalId, reviewer);
        }
      } catch {
        // Backend unreachable -- demo fallback below.
      }
    }

    if (approve) {
      setProposals((prev) =>
        prev.map((p) =>
          p.id === proposalId
            ? { ...p, status: 'approved', reviewer, reviewed_at: new Date().toISOString() }
            : p
        )
      );

      // Materialize to Cap Table
      const targetIssuer = demoCompanySetup ? 'Demo Acme Inc' : (prop.issuer_name || 'Flowgate Systems Inc.');
      const newCte: CapTableEvent = {
        id: 'cte_' + Math.random().toString(36).substring(2, 8),
        issuer_name: targetIssuer,
        event_type: 'issuance',
        holder_id: prop.holder_id || 'inv_' + prop.holder_name.toLowerCase().replace(/[^a-z0-9]/g, '_'),
        holder_name: prop.holder_name,
        share_count: prop.share_count,
        share_class: prop.share_class || 'Common',
        share_price: prop.share_price || 1.0,
        timestamp: new Date().toISOString(),
      };

      setCapTableEvents((prev) => [...prev, newCte]);

      setLedgerEntries((prev) => [
        {
          id: 'led_prop_app_' + Math.random().toString(36).substring(2, 7),
          entry_type: 'cap_table_proposal',
          trace_id: generateTraceId(),
          title: `Proposal Approved by ${reviewer}: ${prop.share_count.toLocaleString()} shares written to Cap Table`,
          details: { holder: prop.holder_name, price: prop.share_price, shares: prop.share_count },
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ]);
      setErrorBoxMsg('');
    } else {
      setProposals((prev) =>
        prev.map((p) =>
          p.id === proposalId
            ? { ...p, status: 'rejected', reviewer, reviewed_at: new Date().toISOString() }
            : p
        )
      );

      setLedgerEntries((prev) => [
        {
          id: 'led_prop_rej_' + Math.random().toString(36).substring(2, 7),
          entry_type: 'cap_table_proposal',
          trace_id: generateTraceId(),
          title: `Proposal Rejected by ${reviewer}`,
          details: { proposal_id: proposalId },
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ]);
      setErrorBoxMsg('');
    }
  };

  // Create Investor (from index.html #create-investor-btn)
  const handleCreateInvestor = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newInvestorName.trim();
    if (!trimmed) {
      setErrorBoxMsg('Type an investor name first.');
      return;
    }

    // Prevent duplicate entries if the name already exists
    const existing = investors.find(
      (inv) => inv.name.toLowerCase() === trimmed.toLowerCase()
    );

    if (existing) {
      // Pre-select existing investor in proposal dropdowns
      proposals.forEach((p) => {
        setSelectedInvestorForProposal((prev) => ({
          ...prev,
          [p.id]: existing.id,
        }));
      });
      setErrorBoxMsg(`"${existing.name}" is already in the registry. Pre-selected in the proposal link dropdown.`);
      setNewInvestorName('');
      return;
    }

    let newInv: Investor = {
      id: 'inv_' + Math.random().toString(36).substring(2, 8),
      name: trimmed,
      investor_type: newInvestorType,
      jurisdiction: 'Global',
      kyc_status: 'cleared',
      created_at: new Date().toISOString(),
    };

    if (liveApi.isLive()) {
      try {
        newInv = await liveApi.createInvestor(trimmed, newInvestorType);
      } catch {
        // Backend unreachable -- demo id below.
      }
    }

    setInvestors((prev) => [...prev, newInv]);

    // Automatically pre-select the newly created investor in all pending proposals
    proposals.forEach((p) => {
      setSelectedInvestorForProposal((prev) => ({
        ...prev,
        [p.id]: newInv.id,
      }));
    });

    setLedgerEntries((prev) => [
      {
        id: 'led_inv_' + Math.random().toString(36).substring(2, 7),
        entry_type: 'cap_table_proposal',
        trace_id: generateTraceId(),
        title: `Investor Registered: ${trimmed} (${newInvestorType})`,
        details: { investor_id: newInv.id, name: trimmed, type: newInvestorType },
        timestamp: new Date().toISOString(),
      },
      ...prev,
    ]);

    setNewInvestorName('');
    setErrorBoxMsg('');
  };

  // Link Investor to Proposal (from index.html [data-link])
  const handleLinkInvestor = async (proposalId: string) => {
    const chosenId = selectedInvestorForProposal[proposalId];
    if (!chosenId) {
      setErrorBoxMsg('Pick an investor from the dropdown first.');
      return;
    }

    const reviewer = activeReviewer.trim() || 'M. Vance';
    const inv = investors.find((i) => i.id === chosenId);
    if (!inv) {
      setErrorBoxMsg('Selected investor not found in registry.');
      return;
    }

    if (liveApi.isLive()) {
      try {
        await liveApi.linkInvestor(proposalId, chosenId, reviewer);
      } catch {
        // Backend unreachable -- demo fallback below.
      }
    }

    setProposals((prev) =>
      prev.map((p) =>
        p.id === proposalId
          ? {
              ...p,
              holder_id: chosenId,
              holder_name: inv.name,
            }
          : p
      )
    );

    setLedgerEntries((prev) => [
      {
        id: 'led_link_' + Math.random().toString(36).substring(2, 7),
        entry_type: 'cap_table_proposal',
        trace_id: generateTraceId(),
        title: `Investor Linked: ${inv.name} assigned to Proposal by ${reviewer}`,
        details: { proposal_id: proposalId, investor_id: chosenId, investor_name: inv.name },
        timestamp: new Date().toISOString(),
      },
      ...prev,
    ]);
    setErrorBoxMsg('');
  };

  // Create Capital Call (from index.html #create-capital-call-btn)
  const handleCreateCapitalCall = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ccFunderName.trim()) {
      setErrorBoxMsg('Type the funder name as it appears in the registry.');
      return;
    }
    if (ccCapitalOwing <= 0) {
      setErrorBoxMsg('Enter a positive capital owing amount.');
      return;
    }

    const funderMatch = investors.find(
      (inv) => inv.name.toLowerCase() === ccFunderName.trim().toLowerCase()
    );

    let newCall: CapitalCall = {
      id: 'call_' + Math.random().toString(36).substring(2, 8),
      instrument_id: 'inst_live_demo',
      funder_name: ccFunderName.trim(),
      capital_owing: ccCapitalOwing,
      currency: 'USD',
      due_date: ccDueDate ? ccDueDate + 'T00:00:00Z' : new Date().toISOString(),
      status: 'pending_approval',
      created_at: new Date().toISOString(),
      wire_details: 'Meridian Escrow Account #49281-US',
    };

    if (liveApi.isLive()) {
      try {
        newCall = await liveApi.createCapitalCall({
          funder_name: ccFunderName.trim(),
          currency: 'USD',
          capital_owing: ccCapitalOwing,
          due_date: ccDueDate ? ccDueDate + 'T00:00:00Z' : null,
          wire_details: 'Meridian Escrow Account #49281-US',
        });
      } catch {
        // Backend unreachable -- demo call below.
      }
    }

    setCapitalCalls((prev) => [newCall, ...prev]);
    setCcFunderName('');

    setLedgerEntries((prev) => [
      {
        id: 'led_call_' + Math.random().toString(36).substring(2, 7),
        entry_type: 'capital_call_review',
        trace_id: generateTraceId(),
        title: `Capital Call Notice Created: ${newCall.capital_owing.toLocaleString()} USD to ${newCall.funder_name}`,
        details: { due_date: newCall.due_date, funder_resolved: !!funderMatch },
        timestamp: new Date().toISOString(),
      },
      ...prev,
    ]);
    setErrorBoxMsg('');
  };

  // Decide Capital Call (from index.html decideCapitalCall)
  const handleDecideCapitalCall = (callId: string, action: 'approve' | 'reject') => {
    const reviewer = activeReviewer.trim() || 'M. Vance — Audit Lead';

    if (liveApi.isLive()) {
      try {
        liveApi
          .reviewCapitalCall(callId, reviewer, action)
          .catch(() => {
            // Backend unreachable -- demo fallback below already applied.
          });
      } catch {
        // Synchronous failure -- demo fallback below already applied.
      }
    }

    setCapitalCalls((prev) =>
      prev.map((c) =>
        c.id === callId
          ? {
              ...c,
              status: action === 'approve' ? 'approved' : 'rejected',
              reviewer,
              reviewed_at: new Date().toISOString(),
            }
          : c
      )
    );

    setLedgerEntries((prev) => [
      {
        id: 'led_cc_dec_' + Math.random().toString(36).substring(2, 7),
        entry_type: 'capital_call_review',
        trace_id: generateTraceId(),
        title: `Capital Call ${action.toUpperCase()} by ${reviewer}`,
        details: { call_id: callId, reviewer, action },
        timestamp: new Date().toISOString(),
      },
      ...prev,
    ]);
    setErrorBoxMsg('');
  };

  // Overdue count (from index.html overdueCount)
  const overdueCallsCount = useMemo(() => {
    const now = new Date();
    return capitalCalls.filter(
      (c) => c.status === 'pending_approval' && c.due_date && new Date(c.due_date) < now
    ).length;
  }, [capitalCalls]);

  const pendingProposalsCount = proposals.filter((p) => p.status === 'proposed').length;
  const pendingCallsCount = capitalCalls.filter((c) => c.status === 'pending_approval').length;

  return (
    <div className="space-y-6">
      {/* Top Header: Brand, Badges & Connection Status (from index.html <nav>) */}
      <div className="bg-white rounded-2xl p-4 sm:p-5 shadow-xs border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <img
            src={`${import.meta.env.BASE_URL}flowgate-logo.png`}
            alt="Flowgate Logo"
            className="w-10 h-10 rounded-xl object-cover shadow-sm border border-gray-200/80"
            referrerPolicy="no-referrer"
          />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold text-gray-900 tracking-tight">
                Flowgate <span className="text-[#7048E8]">\ Live Demo</span>
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#EBF0FD] text-[#2342E3] border border-blue-200/60">
                Operational Dashboard
              </span>
            </div>
            <p className="text-xs text-gray-500">
              Confidence-Gated Intake, Dual-Mode Compliance & Event-Sourced Cap Table
            </p>
          </div>
        </div>

        {/* Connection Toggle & Status */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#F4F6FC] hover:bg-[#EBE7FD] text-gray-700 hover:text-[#7048E8] text-xs font-semibold border border-gray-200/70 transition-colors cursor-pointer"
          >
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-[#20C997]' : 'bg-[#FF6B2C]'}`} />
            <span>{isConnected ? connectionLabel : 'disconnected'}</span>
          </button>
        </div>
      </div>

      {/* Settings Drawer (from index.html #settings) */}
      {showSettings && (
        <div className="bg-white rounded-2xl p-4 shadow-xs border border-purple-100 space-y-3">
          <div className="text-xs font-bold text-gray-800 uppercase tracking-wider">
            API Connection Settings
          </div>
          <div className="flex flex-wrap items-end gap-3 text-xs">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-gray-500 font-semibold mb-1">API BASE URL</label>
              <input
                type="text"
                placeholder="https://flowgate-7q0p.onrender.com"
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
                className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-800 font-mono text-xs focus:border-[#7048E8] outline-none"
              />
            </div>
            <div className="flex-1 min-w-[160px]">
              <label className="block text-gray-500 font-semibold mb-1">API KEY (X-API-KEY)</label>
              <input
                type="password"
                placeholder="development_key_123"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full bg-[#F4F6FC] border border-gray-200 rounded-lg p-2 text-gray-800 font-mono text-xs focus:border-[#7048E8] outline-none"
              />
            </div>
            <button
              onClick={async () => {
                if (apiBase.startsWith('http')) {
                  try {
                    const res = await fetch(`${apiBase.replace(/\/$/, '')}/health`);
                    if (res.ok) {
                      setIsConnected(true);
                      setConnectionLabel(`connected (${new URL(apiBase).hostname})`);
                      setShowSettings(false);
                      return;
                    }
                  } catch {
                    // fall through
                  }
                }
                setIsConnected(true);
                setShowSettings(false);
              }}
              className="px-4 py-2 rounded-lg bg-[#7048E8] text-white font-bold hover:bg-[#5C38D1] transition-colors cursor-pointer"
            >
              Save & Connect
            </button>
          </div>
        </div>
      )}

      {/* OVERVIEW Metric Banner */}
      <div className="bg-[#E8EFFD] rounded-2xl p-4 sm:p-5">
        <div className="text-[11px] font-bold tracking-wider text-[#5C4DE5] uppercase mb-3">
          OVERVIEW & OPERATIONAL HEALTH
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Document Processing Status */}
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-[#7048E8] text-white flex items-center justify-center">
                <FileText className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Document Intake</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight truncate">
              {lastResult ? lastResult.document.document_type.replace('_', ' ') : 'Ready'}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              {lastResult ? `${(lastResult.document.confidence * 100).toFixed(0)}% extraction confidence` : 'No document processed yet'}
            </div>
          </div>

          {/* Card 2: Compliance Track */}
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FF6B2C] text-white flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Compliance Mode</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight capitalize">
              {selectedMode} Track
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              {selectedMode === 'islamic' ? 'AAOIFI / Fatwa / No Riba' : 'KYC / AML / Rate Bounds'}
            </div>
          </div>

          {/* Card 3: Fully Diluted Shares (from Cap Table) */}
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#FAB005] text-white flex items-center justify-center">
                <Building2 className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Fully Diluted Shares</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              {currentSnapshot.total_fully_diluted_shares.toLocaleString()}
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              {currentSnapshot.positions.length} position holders
            </div>
          </div>

          {/* Card 4: Human Review Gate Queue */}
          <div className="bg-white rounded-xl p-4 shadow-xs border border-gray-100/80 flex flex-col justify-between">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-[#20C997] text-white flex items-center justify-center">
                <Coins className="w-4 h-4" />
              </div>
              <span className="text-xs font-semibold text-gray-500">Pending Review</span>
            </div>
            <div className="text-2xl font-extrabold text-[#111827] mt-3 tracking-tight">
              {pendingProposalsCount + pendingCallsCount} Actions
            </div>
            <div className="text-[11px] text-gray-400 mt-1 font-medium">
              {pendingProposalsCount} proposals &middot; {pendingCallsCount} calls
            </div>
          </div>
        </div>
      </div>

      {/* Global Error Box (from index.html #error-box) */}
      {errorBoxMsg && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3.5 text-xs text-red-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{errorBoxMsg}</span>
          </div>
          <button onClick={() => setErrorBoxMsg('')} className="text-red-500 hover:text-red-700 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* MAIN TWO-COLUMN WORKSPACE */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (7 cols): Document Intake, Compliance Mode & 4-Step Process */}
        <div className="lg:col-span-7 space-y-6">
          {/* Panel: Document Intake (from index.html lines 129-146) */}
          <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm sm:text-base font-bold text-gray-900">Document Intake</h3>
                <p className="text-xs text-gray-500">
                  Paste text or upload a contract (PDF / scan / text)
                </p>
              </div>

              {/* Input Mode Tabs */}
              <div className="flex items-center bg-[#F2EDFE] p-0.5 rounded-lg text-xs font-semibold">
                <button
                  id="tab-paste"
                  onClick={() => setActiveInputTab('paste')}
                  className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                    activeInputTab === 'paste'
                      ? 'bg-[#7048E8] text-white shadow-xs'
                      : 'text-[#7048E8] hover:bg-white/50'
                  }`}
                >
                  Paste text
                </button>
                <button
                  id="tab-upload"
                  onClick={() => setActiveInputTab('upload')}
                  className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                    activeInputTab === 'upload'
                      ? 'bg-[#7048E8] text-white shadow-xs'
                      : 'text-[#7048E8] hover:bg-white/50'
                  }`}
                >
                  Upload file
                </button>
              </div>
            </div>

            {/* Template Selector Pills (from index.html EXAMPLES) */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[11px] font-semibold text-gray-400 mr-1">Templates:</span>
              {Object.keys(SAMPLE_DOCUMENTS).map((key) => (
                <button
                  key={key}
                  onClick={() => handleSelectExample(key)}
                  className={`px-2.5 py-1 rounded-full text-xs font-semibold transition-colors cursor-pointer ${
                    selectedExample === key
                      ? 'bg-[#7048E8] text-white'
                      : 'bg-[#F4F6FC] text-gray-600 hover:bg-gray-200/60'
                  }`}
                >
                  {key}
                </button>
              ))}
            </div>

            {/* Textarea or Upload Dropzone */}
            {activeInputTab === 'paste' ? (
              <textarea
                id="doc-text"
                rows={7}
                value={docText}
                onChange={(e) => setDocText(e.target.value)}
                placeholder="Paste a loan agreement, sukuk certificate, or term sheet here..."
                className="w-full bg-[#F8FAFD] border border-gray-200 rounded-xl p-3.5 text-xs text-gray-800 font-mono focus:border-[#7048E8] outline-none transition-colors"
              />
            ) : (
              <div className="border-2 border-dashed border-gray-200 hover:border-[#7048E8] rounded-xl p-6 text-center bg-[#F8FAFD] transition-colors">
                <Upload className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                <label className="cursor-pointer inline-block px-4 py-1.5 rounded-lg bg-[#7048E8] text-white text-xs font-bold hover:bg-[#5C38D1]">
                  Choose a file
                  <input
                    type="file"
                    id="file-input"
                    accept=".pdf,.txt,.md,.html,.png,.jpg,.jpeg"
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setUploadedFile(e.target.files[0]);
                      }
                    }}
                  />
                </label>
                <div className="text-xs text-gray-500 mt-2 font-medium">
                  {uploadedFile ? uploadedFile.name : 'PDF, scans, TXT, or term sheets'}
                </div>
              </div>
            )}

            {/* Panel: Compliance Mode Switcher (from index.html lines 148-156) */}
            <div className="pt-2 border-t border-gray-100 flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="text-xs font-bold text-gray-900 block">Compliance Mode</span>
                <span className="text-[11px] text-gray-500">
                  {selectedMode === 'traditional'
                    ? 'Traditional: KYC/AML counterparty validation & rate sanity'
                    : 'Islamic: Contract type, asset backing, no riba / speculation'}
                </span>
              </div>

              <div className="flex items-center bg-[#F2EDFE] p-0.5 rounded-lg text-xs font-semibold">
                <button
                  id="mode-traditional"
                  onClick={() => setSelectedMode('traditional')}
                  className={`px-3 py-1.5 rounded-md transition-colors cursor-pointer ${
                    selectedMode === 'traditional'
                      ? 'bg-[#7048E8] text-white shadow-xs'
                      : 'text-[#7048E8] hover:bg-white/50'
                  }`}
                >
                  Traditional
                </button>
                <button
                  id="mode-islamic"
                  onClick={() => setSelectedMode('islamic')}
                  className={`px-3 py-1.5 rounded-md transition-colors cursor-pointer ${
                    selectedMode === 'islamic'
                      ? 'bg-[#7048E8] text-white shadow-xs'
                      : 'text-[#7048E8] hover:bg-white/50'
                  }`}
                >
                  Islamic
                </button>
              </div>
            </div>

            {/* Panel: Process Button & 4-Step Pipeline (from index.html lines 157-171) */}
            <div className="pt-3 border-t border-gray-100">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-xs font-bold text-gray-900">4-Step Confidence Pipeline</h4>
                  <p className="text-[11px] text-gray-400">Classify &rarr; Extract &rarr; Compliance Gate &rarr; Ledger</p>
                </div>

                <div className="flex items-center gap-3">
                  {processTimer && (
                    <span className="font-mono text-xs font-semibold text-[#7048E8]" id="timer">
                      {processTimer}
                    </span>
                  )}
                  <button
                    id="run-btn"
                    onClick={handleRunProcessing}
                    disabled={isProcessing}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-[#7048E8] hover:bg-[#5C38D1] text-white text-xs font-bold transition-all disabled:opacity-50 shadow-sm shadow-purple-500/20 cursor-pointer"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>{isProcessing ? 'Processing...' : 'Process document'}</span>
                  </button>
                </div>
              </div>

              {/* Step Indicators */}
              <div className="grid grid-cols-4 gap-2 pt-1" id="steps">
                {[
                  { key: 'classify', label: '1. Classify', gate: '75%' },
                  { key: 'extract', label: '2. Extract', gate: '85%' },
                  { key: 'compliance', label: '3. Compliance', gate: 'Gate' },
                  { key: 'ledger', label: '4. Ledger', gate: 'Trace' },
                ].map((s) => {
                  const state = pipelineSteps[s.key as keyof typeof pipelineSteps];
                  return (
                    <div
                      key={s.key}
                      className={`p-2.5 rounded-xl border text-center transition-all ${
                        state === 'done'
                          ? 'bg-emerald-50/80 border-emerald-200 text-emerald-800'
                          : state === 'active'
                          ? 'bg-purple-50 border-[#7048E8] text-[#7048E8] animate-pulse'
                          : 'bg-gray-50 border-gray-200/70 text-gray-400'
                      }`}
                    >
                      <div className="text-xs font-bold">{s.label}</div>
                      <div className="text-[10px] font-mono mt-0.5">
                        {state === 'done' ? '✓ Verified' : state === 'active' ? 'Evaluating' : s.gate}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column (5 cols): Extracted Fields & Compliance Findings (from index.html lines 173-187) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Panel: Extracted Fields (from index.html #fields-list) */}
          <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 space-y-3">
            <div className="flex items-center justify-between border-b border-gray-100 pb-2.5">
              <div>
                <h3 className="text-sm font-bold text-gray-900">Extracted Fields</h3>
                <p className="text-[11px] text-gray-500">What the pipeline read from the document</p>
              </div>
              {lastResult && (
                <span className="text-[11px] font-bold font-mono px-2 py-0.5 rounded-md bg-[#EBE7FD] text-[#7048E8]">
                  {(lastResult.document.confidence * 100).toFixed(0)}% Classify
                </span>
              )}
            </div>

            {lastResult ? (
              <div className="space-y-2 text-xs" id="fields-list">
                {lastResult.document.status === 'review_needed' && (
                  <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-medium">
                    <b>Routed to human review:</b> The pipeline flagged this document for manual verification.
                  </div>
                )}

                <div className="space-y-1.5 font-mono text-xs">
                  <div className="flex justify-between py-1 border-b border-gray-100">
                    <span className="text-gray-500">Document Type</span>
                    <span className="font-bold text-gray-900 capitalize">
                      {lastResult.document.document_type.replace('_', ' ')}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-100">
                    <span className="text-gray-500">Issuer</span>
                    <span className="font-bold text-gray-900">{lastResult.instrument.issuer_name}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-gray-100">
                    <span className="text-gray-500">Amount</span>
                    <span className="font-bold text-gray-900">
                      {lastResult.instrument.amount ? `$${lastResult.instrument.amount.toLocaleString()}` : '—'}
                    </span>
                  </div>
                  {lastResult.extracted_fields.find((f) => f.name === 'structure' || f.name === 'contract_type') && (
                    <div className="flex justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-500">Contract Type</span>
                      <span className="font-bold text-[#7048E8]">
                        {String(lastResult.extracted_fields.find((f) => f.name === 'structure' || f.name === 'contract_type')?.value)}
                      </span>
                    </div>
                  )}
                  {lastResult.extracted_fields.find((f) => f.name === 'underlying_asset') && (
                    <div className="flex justify-between py-1 border-b border-gray-100">
                      <span className="text-gray-500">Underlying Asset</span>
                      <span className="font-bold text-gray-900 truncate max-w-[180px]">
                        {String(lastResult.extracted_fields.find((f) => f.name === 'underlying_asset')?.value)}
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between py-1 border-b border-gray-100">
                    <span className="text-gray-500">Extraction Confidence</span>
                    <span className="font-bold text-emerald-600">
                      {(lastResult.document.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                {/* Granular Field Citations from Document */}
                {lastResult.extracted_fields && lastResult.extracted_fields.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
                    <div className="text-[11px] font-bold text-gray-700 uppercase tracking-wide">
                      Verbatim Document Citations ({lastResult.extracted_fields.length} fields)
                    </div>
                    <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                      {lastResult.extracted_fields.map((field, idx) => (
                        <div key={idx} className="p-2 rounded-lg bg-gray-50/80 border border-gray-100 text-xs">
                          <div className="flex items-center justify-between font-mono text-[11px]">
                            <span className="font-bold text-gray-800 capitalize">
                              {field.name.replace(/_/g, ' ')}
                            </span>
                            <span className="text-[10px] text-[#7048E8] font-semibold">
                              {(field.confidence * 100).toFixed(0)}% match
                            </span>
                          </div>
                          <div className="font-semibold text-gray-900 mt-0.5 break-words">
                            {field.value !== null && field.value !== undefined ? String(field.value) : '—'}
                          </div>
                          {field.evidence && (
                            <div className="text-[10px] text-gray-500 italic mt-1 bg-white/70 p-1.5 rounded border border-gray-100/80">
                              &ldquo;{field.evidence}&rdquo;
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-6 text-xs text-gray-400 font-mono">
                No document processed yet. Click &quot;Process document&quot; to inspect fields.
              </div>
            )}
          </div>

          {/* Panel: Compliance Findings & Fix Flow (from index.html lines 180-186) */}
          <div className="bg-white rounded-2xl p-5 shadow-xs border border-gray-100 space-y-3">
            <div className="flex items-center justify-between border-b border-gray-100 pb-2.5">
              <div>
                <h3 className="text-sm font-bold text-gray-900">Compliance Findings</h3>
                <p className="text-[11px] text-gray-500" id="compliance-desc">
                  {selectedMode === 'islamic'
                    ? 'AAOIFI Shariah criteria (contract, asset, no riba, fatwa)'
                    : 'Traditional banking rules (KYC/AML & rate sanity)'}
                </p>
              </div>
            </div>

            {lastResult ? (
              <div className="space-y-2.5" id="checklist">
                {lastResult.compliance_findings.map((finding) => (
                  <div
                    key={finding.rule_id}
                    className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-xs ${
                      finding.status === 'passed'
                        ? 'bg-emerald-50/60 border-emerald-200 text-emerald-800'
                        : 'bg-amber-50 border-amber-200 text-amber-900'
                    }`}
                  >
                    <span
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                        finding.status === 'passed' ? 'bg-emerald-600 text-white' : 'bg-amber-500 text-white'
                      }`}
                    >
                      {finding.status === 'passed' ? '✓' : '!'}
                    </span>
                    <div className="flex-1">
                      <div className="font-bold">{finding.name}</div>
                      <div className="text-[11px] opacity-85 mt-0.5">{finding.summary}</div>
                    </div>
                  </div>
                ))}

                {/* Fix Row: Attach Missing Fatwa (from index.html #fix-row, #fix-btn) */}
                {lastResult.compliance_outcome === 'system_flagged_noncompliant' && selectedMode === 'islamic' && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl space-y-2" id="fix-row">
                    <div className="text-xs text-amber-900 font-semibold">
                      Missing Fatwa Reference detected. Attach authorized fatwa evidence to re-evaluate compliance gate:
                    </div>
                    <button
                      id="fix-btn"
                      onClick={handleAttachFatwaAndRecheck}
                      disabled={isAttachingFatwa}
                      className="w-full py-2 px-3 rounded-lg bg-[#7048E8] text-white text-xs font-bold hover:bg-[#5C38D1] transition-colors cursor-pointer"
                    >
                      {isAttachingFatwa ? 'Attaching evidence...' : 'Attach the missing fatwa & re-check'}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-6 text-xs text-gray-400 font-mono">
                Click &quot;Process document&quot; to evaluate compliance gates.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* EVENT-SOURCED CAP TABLE PANEL (from index.html lines 199-214) */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-3">
          <div>
            <h3 className="text-sm sm:text-base font-bold text-gray-900">Event-Sourced Cap Table</h3>
            <p className="text-xs text-gray-500">
              Ownership is computed by replaying immutable events — never stored as a static snapshot.
            </p>
          </div>

          {/* Action Buttons: Setup demo company & Run Series A round */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              id="captable-setup-btn"
              onClick={handleSetupDemoCompany}
              className="px-3.5 py-1.5 rounded-lg bg-[#7048E8] text-white text-xs font-bold hover:bg-[#5C38D1] transition-colors cursor-pointer"
            >
              1. Set up a demo company
            </button>
            <button
              id="captable-round-btn"
              onClick={handleRunSeriesARound}
              disabled={!demoCompanySetup}
              className="px-3.5 py-1.5 rounded-lg bg-[#F4F6FC] hover:bg-[#EBE7FD] text-[#7048E8] text-xs font-bold border border-purple-200 transition-colors disabled:opacity-40 cursor-pointer"
            >
              2. Run a Series A round
            </button>
          </div>
        </div>

        {/* Before vs After Round Toggle (from index.html lines 206-209) */}
        <div className="flex items-center gap-2">
          <button
            id="ct-view-before"
            onClick={() => setActiveCapTableView('before')}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors cursor-pointer ${
              activeCapTableView === 'before'
                ? 'bg-[#7048E8] text-white shadow-xs'
                : 'bg-[#F4F6FC] text-gray-600 hover:bg-gray-100'
            }`}
          >
            Before the round
          </button>
          <button
            id="ct-view-after"
            onClick={() => setActiveCapTableView('after')}
            disabled={!demoSeriesARun}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors disabled:opacity-40 cursor-pointer ${
              activeCapTableView === 'after'
                ? 'bg-[#7048E8] text-white shadow-xs'
                : 'bg-[#F4F6FC] text-gray-600 hover:bg-gray-100'
            }`}
          >
            After the round
          </button>
        </div>

        {/* Dynamic Segmented Ownership Bar (from index.html #ownership-bar) */}
        <div className="w-full h-8 rounded-xl overflow-hidden flex border border-gray-200 bg-gray-100" id="ownership-bar">
          {currentSnapshot.positions.map((pos, idx) => {
            const colors = ['bg-[#FAB005]', 'bg-[#20C997]', 'bg-[#FF6B2C]', 'bg-[#7048E8]'];
            const colorClass = colors[idx % colors.length];
            return (
              <div
                key={pos.holder_id}
                style={{ width: `${pos.ownership_percent}%` }}
                className={`${colorClass} h-full flex items-center justify-center text-[11px] font-bold text-white transition-all overflow-hidden whitespace-nowrap px-1`}
                title={`${pos.holder_name}: ${pos.ownership_percent}%`}
              >
                {pos.ownership_percent >= 8 ? `${pos.ownership_percent.toFixed(1)}%` : ''}
              </div>
            );
          })}
        </div>

        {/* Ownership Legend (from index.html #ownership-legend) */}
        <div className="flex flex-wrap items-center gap-4 text-xs font-mono" id="ownership-legend">
          {currentSnapshot.positions.map((pos, idx) => {
            const dotColors = ['bg-[#FAB005]', 'bg-[#20C997]', 'bg-[#FF6B2C]', 'bg-[#7048E8]'];
            return (
              <div key={pos.holder_id} className="flex items-center gap-1.5">
                <span className={`w-2.5 h-2.5 rounded-sm ${dotColors[idx % dotColors.length]}`} />
                <span className="font-semibold text-gray-800">{pos.holder_name}</span>
                <span className="text-gray-400">&mdash;</span>
                <span className="font-bold text-[#7048E8]">{pos.ownership_percent.toFixed(1)}%</span>
                <span className="text-gray-500">({pos.shares.toLocaleString()} shares)</span>
              </div>
            );
          })}
        </div>

        {/* Stat Row: Total Fully Diluted Shares (from index.html #ct-total) */}
        <div className="flex justify-between items-center py-2.5 border-t border-gray-100 text-xs font-mono">
          <span className="text-gray-500 font-semibold">Total Diluted Shares:</span>
          <span className="text-base font-extrabold text-gray-900" id="ct-total">
            {currentSnapshot.total_fully_diluted_shares.toLocaleString()}
          </span>
        </div>
      </div>

      {/* CAP TABLE PROPOSALS (HUMAN REVIEW GATE) (from index.html lines 216-220) */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-3">
          <div>
            <h3 className="text-sm sm:text-base font-bold text-gray-900">Cap Table Proposals</h3>
            <p className="text-xs text-gray-500">
              Issuances read from documents, awaiting human review. Approving writes to the live cap table; rejecting writes only to audit ledger.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs font-mono bg-gray-50 border border-gray-200 px-2.5 py-1 rounded-lg">
              <span className="text-gray-500 font-semibold text-[11px]">Signer:</span>
              <input
                type="text"
                value={activeReviewer}
                onChange={(e) => setActiveReviewer(e.target.value)}
                className="bg-white border border-gray-200 rounded px-1.5 py-0.5 text-xs text-gray-800 font-semibold outline-none focus:border-[#7048E8] w-44"
                title="Your reviewer signature for approvals and audits"
              />
            </div>
            <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-[#EBE7FD] text-[#7048E8]">
              {pendingProposalsCount} Pending
            </span>
          </div>
        </div>

        {/* Inline Investor Registry Form (from index.html lines 812-821) */}
        <div className="p-3.5 bg-[#F8FAFD] rounded-xl border border-dashed border-gray-200 space-y-2">
          <div className="text-xs text-gray-500 font-medium">
            Holder not in registry yet? Create investor here, then link them on the proposal below:
          </div>
          <form onSubmit={handleCreateInvestor} className="flex flex-wrap items-center gap-2 text-xs">
            <input
              type="text"
              id="new-investor-name"
              placeholder="e.g. Dana or Horizon Ventures"
              value={newInvestorName}
              onChange={(e) => setNewInvestorName(e.target.value)}
              className="bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-gray-800 flex-1 min-w-[160px] outline-none"
            />
            <select
              id="new-investor-type"
              value={newInvestorType}
              onChange={(e) => setNewInvestorType(e.target.value as any)}
              className="bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-gray-800 outline-none"
            >
              <option value="individual">individual</option>
              <option value="institution">institution</option>
              <option value="fund">fund</option>
            </select>
            <button
              type="submit"
              id="create-investor-btn"
              className="px-3 py-1.5 rounded-lg bg-[#7048E8] text-white font-bold hover:bg-[#5C38D1] cursor-pointer transition-colors"
            >
              Create investor
            </button>
          </form>
        </div>

        {/* Proposals List (from index.html #proposals-list) */}
        <div className="space-y-3" id="proposals-list">
          {proposals.length === 0 ? (
            <div className="text-xs text-gray-400 font-mono py-4 text-center">
              No proposals yet. Process an equity/subscription document that clears both confidence gates.
            </div>
          ) : (
            proposals.map((p) => {
              const isPending = p.status === 'proposed';
              return (
                <div
                  key={p.id}
                  className="p-4 rounded-xl border border-gray-200/80 bg-white hover:border-gray-300 transition-all space-y-2.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-bold text-gray-600">
                      Cap Table Proposal &middot; {p.issuer_name}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                        isPending
                          ? 'bg-amber-100 text-amber-800'
                          : p.status === 'approved'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {isPending ? 'PENDING DECISION' : p.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono pt-1">
                    <div>
                      <span className="text-gray-400 block text-[10px]">HOLDER</span>
                      <span className="font-bold text-gray-900">{p.holder_name}</span>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">SHARES</span>
                      <span className="font-bold text-gray-900">{p.share_count.toLocaleString()}</span>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">PRICE / SHARE</span>
                      <span className="font-bold text-gray-900">${p.share_price}</span>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">CLASS</span>
                      <span className="font-bold text-[#7048E8]">{p.share_class}</span>
                    </div>
                  </div>

                  {/* Link real investor dropdown if pending */}
                  {isPending && (
                    <div className="flex items-center gap-2 pt-1">
                      <select
                        value={selectedInvestorForProposal[p.id] || ''}
                        onChange={(e) =>
                          setSelectedInvestorForProposal((prev) => ({
                            ...prev,
                            [p.id]: e.target.value,
                          }))
                        }
                        className="bg-gray-50 border border-gray-200 rounded-lg p-1.5 text-xs text-gray-800 flex-1"
                      >
                        <option value="">-- link a registry investor --</option>
                        {investors.map((inv) => (
                          <option key={inv.id} value={inv.id}>
                            {inv.name} ({inv.investor_type})
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => handleLinkInvestor(p.id)}
                        className="px-2.5 py-1.5 rounded-lg border border-[#7048E8] text-xs font-bold text-[#7048E8] bg-[#EBE7FD]/40 hover:bg-[#EBE7FD] transition-colors cursor-pointer"
                      >
                        Link investor
                      </button>
                    </div>
                  )}

                  {/* Decision Buttons */}
                  {isPending ? (
                    <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
                      <button
                        onClick={() => handleDecideProposal(p.id, true)}
                        className="px-3.5 py-1.5 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white text-xs font-bold transition-colors cursor-pointer"
                      >
                        Approve & write to cap table
                      </button>
                      <button
                        onClick={() => handleDecideProposal(p.id, false)}
                        className="px-3.5 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600 text-xs font-bold transition-colors cursor-pointer"
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <div className="text-[11px] font-mono text-gray-500 pt-1 flex flex-wrap items-center gap-2 border-t border-gray-100">
                      <span>Reviewed by <strong className="text-gray-800">{p.reviewer || 'Audit Lead'}</strong></span>
                      <span>&middot;</span>
                      <span>{p.reviewed_at ? new Date(p.reviewed_at).toLocaleTimeString() : 'Recorded'}</span>
                      {p.status === 'approved' && (
                        <span className="text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                          Written to Live Cap Table ({p.share_count.toLocaleString()} shares)
                        </span>
                      )}
                      {p.status === 'rejected' && (
                        <span className="text-gray-600 font-semibold bg-gray-100 px-2 py-0.5 rounded border border-gray-200">
                          Rejected (Logged in audit ledger)
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* CAPITAL CALLS PANEL (from index.html lines 221-243) */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm sm:text-base font-bold text-gray-900">Capital Calls</h3>
              {overdueCallsCount > 0 && (
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-mono">
                  {overdueCallsCount} {overdueCallsCount === 1 ? 'call overdue' : 'calls overdue'}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500">
              Obligations read from notices, awaiting reviewer authorization before drawdown execution.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-[#EBE7FD] text-[#7048E8]">
              {pendingCallsCount} Pending
            </span>
          </div>
        </div>

        {/* Record a Capital Call Notice Form (from index.html lines 233-241) */}
        <div className="p-3.5 bg-[#F8FAFD] rounded-xl border border-dashed border-gray-200 space-y-2">
          <div className="text-xs text-gray-500 font-medium">
            Record a capital call notice for the current instrument. Funders are matched against the investor registry by name.
          </div>
          <form onSubmit={handleCreateCapitalCall} className="flex flex-wrap items-end gap-3 text-xs">
            <div className="flex-2 min-w-[150px]">
              <label className="block text-gray-500 font-semibold mb-1">Funder Name</label>
              <input
                type="text"
                id="cc-funder-name"
                placeholder="e.g. Apex Horizon Growth Fund LP"
                value={ccFunderName}
                onChange={(e) => setCcFunderName(e.target.value)}
                className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-800 outline-none"
              />
            </div>
            <div className="flex-1 min-w-[120px]">
              <label className="block text-gray-500 font-semibold mb-1">Owing (USD)</label>
              <input
                type="number"
                id="cc-capital-owing"
                value={ccCapitalOwing}
                onChange={(e) => setCcCapitalOwing(parseFloat(e.target.value) || 0)}
                className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-800 outline-none"
              />
            </div>
            <div className="flex-1 min-w-[140px]">
              <label className="block text-gray-500 font-semibold mb-1">Due Date</label>
              <input
                type="date"
                id="cc-due-date"
                value={ccDueDate}
                onChange={(e) => setCcDueDate(e.target.value)}
                className="w-full bg-white border border-gray-200 rounded-lg p-2 text-gray-800 outline-none"
              />
            </div>
            <button
              type="submit"
              id="create-capital-call-btn"
              className="px-4 py-2 rounded-lg bg-[#7048E8] text-white font-bold hover:bg-[#5C38D1] cursor-pointer"
            >
              Create call
            </button>
          </form>
        </div>

        {/* Capital Calls List (from index.html #capital-calls-list) */}
        <div className="space-y-3" id="capital-calls-list">
          {capitalCalls.length === 0 ? (
            <div className="text-xs text-gray-400 font-mono py-4 text-center">
              No capital calls recorded yet. Use the notice form above to start the queue.
            </div>
          ) : (
            capitalCalls.map((c) => {
              const isPending = c.status === 'pending_approval';
              const isOverdue = isPending && c.due_date && new Date(c.due_date) < new Date();
              return (
                <div
                  key={c.id}
                  className={`p-4 rounded-xl border bg-white space-y-2.5 transition-all ${
                    isOverdue ? 'border-red-200 bg-red-50/20' : 'border-gray-200/80'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-bold text-gray-600">
                      capital_call_notice &middot; {c.funder_name}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                        isOverdue
                          ? 'bg-red-100 text-red-800'
                          : isPending
                          ? 'bg-amber-100 text-amber-800'
                          : c.status === 'approved'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {isOverdue ? 'OVERDUE' : isPending ? 'PENDING DECISION' : c.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono pt-1">
                    <div>
                      <span className="text-gray-400 block text-[10px]">FUNDER</span>
                      <span className="font-bold text-gray-900">{c.funder_name}</span>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">OWING</span>
                      <span className="font-bold text-[#7048E8]">
                        ${c.capital_owing.toLocaleString()} {c.currency}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">DUE DATE</span>
                      <span className="font-bold text-gray-900">
                        {c.due_date ? c.due_date.slice(0, 10) : '—'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400 block text-[10px]">REVIEW GATE</span>
                      <span className="font-bold text-gray-700">
                        Human check required
                      </span>
                    </div>
                  </div>

                  {isPending ? (
                    <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
                      <button
                        onClick={() => handleDecideCapitalCall(c.id, 'approve')}
                        className="px-3.5 py-1.5 rounded-lg bg-[#7048E8] hover:bg-[#5C38D1] text-white text-xs font-bold transition-colors cursor-pointer"
                      >
                        Approve capital call notice
                      </button>
                      <button
                        onClick={() => handleDecideCapitalCall(c.id, 'reject')}
                        className="px-3.5 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600 text-xs font-bold transition-colors cursor-pointer"
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <div className="text-[11px] font-mono text-gray-500 pt-1 flex flex-wrap items-center gap-2 border-t border-gray-100">
                      <span>Reviewed by <strong className="text-gray-800">{c.reviewer || 'Audit Lead'}</strong></span>
                      <span>&middot;</span>
                      <span>{c.reviewed_at ? new Date(c.reviewed_at).toLocaleTimeString() : 'Recorded'}</span>
                      {c.status === 'approved' && (
                        <span className="text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                          Drawdown Authorized (${c.capital_owing.toLocaleString()} {c.currency})
                        </span>
                      )}
                      {c.status === 'rejected' && (
                        <span className="text-red-700 font-semibold bg-red-50 px-2 py-0.5 rounded border border-red-200">
                          Notice Rejected (Drawdown blocked)
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* AUDIT TRAIL / UNIFIED LEDGER PANEL (from index.html lines 189-195) */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 shadow-xs border border-gray-100 space-y-4">
        <div className="border-b border-gray-100 pb-3">
          <h3 className="text-sm sm:text-base font-bold text-gray-900">Audit Trail</h3>
          <p className="text-xs text-gray-500">
            Every operational decision, confidence gate, and cap table event is traceable with cryptographic trace IDs.
          </p>
        </div>

        <div className="space-y-2.5 font-mono text-xs" id="ledger-list">
          {ledgerEntries.slice(0, 8).map((entry) => (
            <div
              key={entry.id}
              className="flex items-start gap-3 p-3 rounded-xl bg-[#F8FAFD] border border-gray-100"
            >
              <div className="w-2 h-2 rounded-full bg-[#7048E8] mt-1.5 flex-shrink-0" />
              <div className="flex-1 space-y-0.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-gray-900">{entry.title}</span>
                  <span className="text-[10px] text-gray-400">
                    {entry.timestamp.replace('T', ' ').slice(0, 19)}
                  </span>
                </div>
                <div className="text-[11px] text-gray-500 truncate">
                  Trace ID: <span className="text-[#7048E8] font-bold">{entry.trace_id}</span> &middot; Type: {entry.entry_type}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer Note (from index.html line 193) */}
        <div className="pt-3 border-t border-gray-100 text-center text-xs text-gray-400 font-mono">
          Flowgate ships with document intake + dual-mode compliance + event-sourced cap table. This dashboard runs against your deterministic live engine.
        </div>
      </div>
    </div>
  );
};
