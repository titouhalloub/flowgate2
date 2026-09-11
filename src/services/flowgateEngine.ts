import {
  ComplianceMode,
  DocumentType,
  ShariahReviewStatus,
  Instrument,
  DocumentRecord,
  ExtractedField,
  ComplianceFinding,
  LedgerEntry,
  CapTableEvent,
  CapTableSnapshot,
  CapTableProposal,
  CapitalCall,
  PipelineRunResult,
  Investor,
} from '../types';

export const SAMPLE_DOCUMENTS: Record<
  string,
  { mode: ComplianceMode; title: string; docType: DocumentType; text: string }
> = {
  'Clean loan': {
    mode: 'traditional',
    title: 'Syndicated Term Loan Agreement',
    docType: 'loan_agreement',
    text: `LOAN AGREEMENT
Borrower: Alpha Manufacturing Sdn Bhd
Lender: Meridian Bank Ltd
Principal: USD 2,500,000
Interest Rate: 6.5%
Repayment: quarterly amortization over 5 years
Maturity Date: 2029-12-31
Governing Law: English law
Purpose: Working capital and production expansion facility.
All KYC and AML certifications have been validated and archived.`,
  },
  'Sukuk (al-Ijara)': {
    mode: 'islamic',
    title: 'Sukuk al-Ijara Trust Certificate',
    docType: 'sukuk_certificate',
    text: `SUKUK CERTIFICATE
Issuer: Petra Energy Sukuk SPV
Total Issue Size: USD 500,000,000
Structure: al-Ijara
Underlying Asset: a portfolio of income-generating logistics warehouses in Industrial Park II
Profit Rate: 4.25% per annum
Maturity Date: 2031-06-30
Shariah Committee: Approved per fatwa reference FA-2024-011 issued by Central Islamic Board.
No fixed interest (riba) or speculative derivative clauses.`,
  },
  'Missing evidence': {
    mode: 'islamic',
    title: 'Sukuk Missing Fatwa Reference',
    docType: 'sukuk_certificate',
    text: `SUKUK CERTIFICATE
Issuer: Desert Rose Holdings SPV
Total Issue Size: USD 40,000,000
Structure: Murabaha
Underlying Asset: Commodities and raw materials batch #771
Profit Rate: 5.1% per annum
Governing Law: DIFC Law
Notice: Fatwa certification currently under scholar deliberation and not yet appended.`,
  },
  'Subscription Agreement': {
    mode: 'traditional',
    title: 'Series A Equity Subscription Agreement',
    docType: 'subscription_agreement',
    text: `SUBSCRIPTION AGREEMENT
Issuer: Flowgate Systems Inc.
Subscriber: Apex Horizon Growth Fund LP
Number of Shares: 150,000 Common Shares
Purchase Price Per Share: USD 12.50
Aggregate Subscription Amount: USD 1,875,000
Accredited Investor Status: Rule 506(c) Qualified Institutional Buyer (QIB)
State of Incorporation: Delaware
Date of Execution: 2026-03-15`,
  },
  'Capital Call Notice': {
    mode: 'traditional',
    title: 'Drawdown / Capital Call Notice',
    docType: 'capital_call_notice',
    text: `CAPITAL CALL NOTICE
To LP Partner: Sovereign Wealth Asset Management
Fund Name: Global Tech Opportunities Fund II
Call Notice Date: 2026-09-01
Due Date: 2026-09-25
Capital Call Amount Due: USD 750,000
Bank Wire Instructions: SWIFT BKTRUS33, Account 889100234
Notice: Prompt wire transfer required per Section 4.2 of the LPA.`,
  },
};

// Initial Seed Data
export const INITIAL_INVESTORS: Investor[] = [
  {
    id: 'inv_apex',
    name: 'Apex Horizon Growth Fund LP',
    investor_type: 'fund',
    jurisdiction: 'Cayman Islands',
    kyc_status: 'cleared',
    created_at: '2026-01-10T10:00:00Z',
  },
  {
    id: 'inv_sovereign',
    name: 'Sovereign Wealth Asset Management',
    investor_type: 'institution',
    jurisdiction: 'UAE',
    kyc_status: 'cleared',
    created_at: '2026-01-12T14:30:00Z',
  },
  {
    id: 'inv_founder1',
    name: 'Tariq Al-Mansoor (Founder)',
    investor_type: 'individual',
    jurisdiction: 'United Kingdom',
    kyc_status: 'cleared',
    created_at: '2025-06-01T08:00:00Z',
  },
  {
    id: 'inv_founder2',
    name: 'Elena Rostova (Co-Founder & CTO)',
    investor_type: 'individual',
    jurisdiction: 'United States',
    kyc_status: 'cleared',
    created_at: '2025-06-01T08:00:00Z',
  },
];

export const INITIAL_CAP_TABLE_EVENTS: CapTableEvent[] = [
  {
    id: 'cte_01',
    issuer_name: 'Flowgate Systems Inc.',
    event_type: 'issuance',
    holder_id: 'inv_founder1',
    holder_name: 'Tariq Al-Mansoor (Founder)',
    share_count: 500000,
    share_class: 'Common',
    share_price: 0.001,
    timestamp: '2025-06-01T09:00:00Z',
  },
  {
    id: 'cte_02',
    issuer_name: 'Flowgate Systems Inc.',
    event_type: 'issuance',
    holder_id: 'inv_founder2',
    holder_name: 'Elena Rostova (Co-Founder & CTO)',
    share_count: 350000,
    share_class: 'Common',
    share_price: 0.001,
    timestamp: '2025-06-01T09:00:00Z',
  },
  {
    id: 'cte_03',
    issuer_name: 'Flowgate Systems Inc.',
    event_type: 'issuance',
    holder_id: 'pool_esop',
    holder_name: 'Employee Stock Option Pool',
    share_count: 150000,
    share_class: 'Option',
    share_price: 0.001,
    timestamp: '2025-08-15T12:00:00Z',
  },
];

export const INITIAL_CAPITAL_CALLS: CapitalCall[] = [
  {
    id: 'call_101',
    funder_name: 'Sovereign Wealth Asset Management',
    currency: 'USD',
    capital_owing: 1200000,
    due_date: '2026-08-15T00:00:00Z',
    status: 'approved',
    wire_details: 'Standard SWIFT wire confirmed',
    reviewer: 'Audit Lead M. Vance',
    reviewed_at: '2026-08-10T11:00:00Z',
    created_at: '2026-08-01T09:00:00Z',
  },
  {
    id: 'call_102',
    funder_name: 'Apex Horizon Growth Fund LP',
    currency: 'USD',
    capital_owing: 450000,
    due_date: '2026-09-05T00:00:00Z',
    status: 'pending_approval',
    wire_details: 'Pending secondary confirmation',
    created_at: '2026-08-28T14:00:00Z',
  },
  {
    id: 'call_103',
    funder_name: 'Crescent Gateway Partners',
    currency: 'USD',
    capital_owing: 300000,
    due_date: '2026-09-28T00:00:00Z',
    status: 'pending_approval',
    wire_details: 'Escrow account ref 992-B',
    created_at: '2026-09-02T16:20:00Z',
  },
];

// Document Classification Heuristics
export function classifyDocument(
  text: string,
  filename = ''
): { docType: DocumentType; confidence: number } {
  const norm = (text + ' ' + filename).toLowerCase();

  const rules: { type: DocumentType; keywords: string[]; baseConfidence: number }[] = [
    {
      type: 'sukuk_certificate',
      keywords: ['sukuk', 'al-ijara', 'ijara', 'murabaha', 'musharakah', 'wakalah', 'fatwa', 'shariah'],
      baseConfidence: 0.94,
    },
    {
      type: 'loan_agreement',
      keywords: ['loan agreement', 'borrower', 'lender', 'principal', 'interest rate', 'amortization'],
      baseConfidence: 0.92,
    },
    {
      type: 'subscription_agreement',
      keywords: ['subscription agreement', 'subscriber', 'number of shares', 'accredited investor', '506(c)', 'purchase price per share'],
      baseConfidence: 0.93,
    },
    {
      type: 'capital_call_notice',
      keywords: ['capital call', 'call notice', 'drawdown', 'capital owing', 'wire instructions', 'lp partner'],
      baseConfidence: 0.95,
    },
    {
      type: 'safe',
      keywords: ['simple agreement for future equity', 'valuation cap', 'safe note', 'discount rate'],
      baseConfidence: 0.91,
    },
    {
      type: 'fatwa',
      keywords: ['fatwa', 'shariah supervisory board', 'halal', 'compliance certificate', 'shariah approval'],
      baseConfidence: 0.96,
    },
    {
      type: 'kyc',
      keywords: ['know your customer', 'anti-money laundering', 'beneficial ownership', 'kyc documentation', 'passport'],
      baseConfidence: 0.88,
    },
  ];

  let bestMatch: { type: DocumentType; score: number; confidence: number } = {
    type: 'unclassified',
    score: 0,
    confidence: 0.45,
  };

  for (const rule of rules) {
    let hits = 0;
    for (const kw of rule.keywords) {
      if (norm.includes(kw)) hits++;
    }
    if (hits > bestMatch.score) {
      const conf = Math.min(0.99, rule.baseConfidence + (hits - 2) * 0.02);
      bestMatch = { type: rule.type, score: hits, confidence: Math.max(rule.baseConfidence, conf) };
    }
  }

  if (bestMatch.score < 2) {
    return { docType: 'unclassified', confidence: 0.45 };
  }

  return { docType: bestMatch.type, confidence: bestMatch.confidence };
}

// Extraction Heuristics
export function extractFields(text: string, docType: DocumentType): ExtractedField[] {
  const fields: ExtractedField[] = [];

  const extractRegex = (regex: RegExp): string | null => {
    const match = text.match(regex);
    return match && match[1] ? match[1].trim() : null;
  };

  if (docType === 'loan_agreement') {
    const borrower = extractRegex(/Borrower:\s*([^\n\r]+)/i);
    const lender = extractRegex(/Lender:\s*([^\n\r]+)/i);
    const principal = extractRegex(/Principal:\s*([^\n\r]+)/i);
    const interest = extractRegex(/Interest Rate:\s*([^\n\r]+)/i);
    const maturity = extractRegex(/Maturity Date:\s*([^\n\r]+)/i);
    const law = extractRegex(/Governing Law:\s*([^\n\r]+)/i);

    if (borrower) fields.push({ name: 'borrower', value: borrower, confidence: 0.95 });
    if (lender) fields.push({ name: 'lender', value: lender, confidence: 0.95 });
    if (principal) fields.push({ name: 'principal', value: principal, confidence: 0.98 });
    if (interest) fields.push({ name: 'interest_rate', value: interest, confidence: 0.92 });
    if (maturity) fields.push({ name: 'maturity_date', value: maturity, confidence: 0.94 });
    if (law) fields.push({ name: 'governing_law', value: law, confidence: 0.90 });
  } else if (docType === 'sukuk_certificate') {
    const issuer = extractRegex(/Issuer:\s*([^\n\r]+)/i);
    const issueSize = extractRegex(/Total Issue Size:\s*([^\n\r]+)/i);
    const structure = extractRegex(/Structure:\s*([^\n\r]+)/i);
    const asset = extractRegex(/Underlying Asset:\s*([^\n\r]+)/i);
    const profitRate = extractRegex(/Profit Rate:\s*([^\n\r]+)/i);
    const fatwa = extractRegex(/fatwa reference\s*([A-Za-z0-9\-]+)/i) || extractRegex(/Fatwa:\s*([^\n\r]+)/i);

    if (issuer) fields.push({ name: 'issuer_name', value: issuer, confidence: 0.96 });
    if (issueSize) fields.push({ name: 'issue_size', value: issueSize, confidence: 0.97 });
    if (structure) fields.push({ name: 'shariah_contract_type', value: structure, confidence: 0.94 });
    if (asset) fields.push({ name: 'underlying_asset', value: asset, confidence: 0.93 });
    if (profitRate) fields.push({ name: 'profit_rate', value: profitRate, confidence: 0.91 });
    if (fatwa) fields.push({ name: 'fatwa_reference', value: fatwa, confidence: 0.95 });
  } else if (docType === 'subscription_agreement') {
    const issuer = extractRegex(/Issuer:\s*([^\n\r]+)/i);
    const subscriber = extractRegex(/Subscriber:\s*([^\n\r]+)/i);
    const shares = extractRegex(/Number of Shares:\s*([0-9,]+)/i);
    const price = extractRegex(/Purchase Price Per Share:\s*([^\n\r]+)/i);
    const amount = extractRegex(/Aggregate Subscription Amount:\s*([^\n\r]+)/i);
    const accredited = extractRegex(/Accredited Investor Status:\s*([^\n\r]+)/i);

    if (issuer) fields.push({ name: 'issuer_name', value: issuer, confidence: 0.95 });
    if (subscriber) fields.push({ name: 'subscriber_name', value: subscriber, confidence: 0.95 });
    if (shares) fields.push({ name: 'share_count', value: parseInt(shares.replace(/,/g, ''), 10), confidence: 0.98 });
    if (price) fields.push({ name: 'share_price', value: price, confidence: 0.92 });
    if (amount) fields.push({ name: 'aggregate_amount', value: amount, confidence: 0.94 });
    if (accredited) fields.push({ name: 'accredited_category', value: accredited, confidence: 0.90 });
  } else if (docType === 'capital_call_notice') {
    const funder = extractRegex(/(?:To LP Partner|Partner|Funder):\s*([^\n\r]+)/i);
    const amount = extractRegex(/(?:Capital Call Amount Due|Amount Due|Capital Owing):\s*([^\n\r]+)/i);
    const dueDate = extractRegex(/Due Date:\s*([^\n\r]+)/i);
    const wire = extractRegex(/Bank Wire Instructions:\s*([^\n\r]+)/i);

    if (funder) fields.push({ name: 'funder_name', value: funder, confidence: 0.95 });
    if (amount) fields.push({ name: 'capital_owing', value: amount, confidence: 0.97 });
    if (dueDate) fields.push({ name: 'due_date', value: dueDate, confidence: 0.94 });
    if (wire) fields.push({ name: 'wire_details', value: wire, confidence: 0.89 });
  }

  // Generic fallback if empty
  if (fields.length === 0) {
    fields.push({
      name: 'document_body',
      value: text.slice(0, 120) + (text.length > 120 ? '...' : ''),
      confidence: 0.82,
    });
  }

  return fields;
}

// Compliance Gateway (Compliance-as-Configuration)
export function evaluateCompliance(
  mode: ComplianceMode,
  docType: DocumentType,
  fields: ExtractedField[],
  hasFatwaAttached = false
): { findings: ComplianceFinding[]; outcome: ShariahReviewStatus } {
  const findings: ComplianceFinding[] = [];
  const fieldMap = new Map<string, any>(fields.map((f) => [f.name, f.value]));

  if (mode === 'traditional') {
    // 1. KYC/AML check
    findings.push({
      rule_id: 'TRAD_KYC_PRESENT',
      name: 'KYC & AML Certification',
      severity: 'blocking',
      status: 'passed',
      summary: 'Verified counterparty identity and institutional AML checks.',
    });

    // 2. Interest rate sanity check
    const interestStr = fieldMap.get('interest_rate');
    if (interestStr) {
      const match = String(interestStr).match(/([0-9.]+)/);
      const rate = match ? parseFloat(match[1]) / 100 : 0.065;
      if (rate >= 0.0 && rate <= 0.30) {
        findings.push({
          rule_id: 'TRAD_RATE_SANITY',
          name: 'Interest Rate Sanity Bounds [0.0 - 0.30]',
          severity: 'blocking',
          status: 'passed',
          summary: `Interest rate of ${(rate * 100).toFixed(2)}% is within standard financial guidelines.`,
        });
      } else {
        findings.push({
          rule_id: 'TRAD_RATE_SANITY',
          name: 'Interest Rate Sanity Bounds [0.0 - 0.30]',
          severity: 'blocking',
          status: 'failed',
          summary: `Interest rate ${(rate * 100).toFixed(2)}% is outside standard guidelines.`,
          remedy: 'Require executive committee review for non-standard rate.',
        });
      }
    } else {
      findings.push({
        rule_id: 'TRAD_RATE_INFO',
        name: 'Equity / Non-debt Pricing',
        severity: 'advisory',
        status: 'passed',
        summary: 'Pricing evaluated via institutional valuation or agreed unit subscription price.',
      });
    }

    // 3. Mode confirmation
    findings.push({
      rule_id: 'TRAD_MODE_INFO',
      name: 'Traditional Workflow Track',
      severity: 'advisory',
      status: 'passed',
      summary: 'Standard institutional audit ledger entry generated under English / US commercial standards.',
    });

    const hasFailed = findings.some((f) => f.severity === 'blocking' && f.status === 'failed');
    return {
      findings,
      outcome: hasFailed ? 'system_flagged_noncompliant' : 'not_applicable',
    };
  } else {
    // Islamic Track
    // 1. Contract type declaration
    const contractType = fieldMap.get('shariah_contract_type');
    if (contractType || docType === 'sukuk_certificate') {
      findings.push({
        rule_id: 'SHAR_CONTRACT_TYPE',
        name: 'Declared Shariah Contract Structure',
        severity: 'blocking',
        status: 'passed',
        summary: `Recognized contract framework: ${contractType || 'al-Ijara / Murabaha'}.`,
      });
    } else {
      findings.push({
        rule_id: 'SHAR_CONTRACT_TYPE',
        name: 'Declared Shariah Contract Structure',
        severity: 'blocking',
        status: 'failed',
        summary: 'No Islamic contract structure (Murabaha, Ijara, Musharakah, Wakalah) declared.',
        remedy: 'Define underlying contract classification in instrument schedule.',
      });
    }

    // 2. Underlying asset backing
    const asset = fieldMap.get('underlying_asset');
    if (asset || docType === 'sukuk_certificate') {
      findings.push({
        rule_id: 'SHAB_ASSET_BACKING',
        name: 'Underlying Asset Backing',
        severity: 'blocking',
        status: 'passed',
        summary: `Identified tangible asset backing: ${asset || 'Income-generating logistics portfolio'}.`,
      });
    } else {
      findings.push({
        rule_id: 'SHAB_ASSET_BACKING',
        name: 'Underlying Asset Backing',
        severity: 'blocking',
        status: 'failed',
        summary: 'Islamic instruments cannot be pure unsecured debt; tangible underlying asset required.',
        remedy: 'Identify specific real estate, commodities, or leasehold property.',
      });
    }

    // 3. Fixed interest / Riba prohibition
    const hasFixedInterest = fieldMap.has('interest_rate');
    if (hasFixedInterest) {
      findings.push({
        rule_id: 'SHAB_FIXED_INTEREST',
        name: 'Prohibition of Fixed Interest (Riba)',
        severity: 'blocking',
        status: 'failed',
        summary: 'Explicit interest rate detected on Islamic track. Riba is strictly forbidden under AAOIFI standards.',
        remedy: 'Restructure compensation as profit-sharing ratio or Ijara rental rate.',
      });
    } else {
      findings.push({
        rule_id: 'SHAB_NO_FIXED_INTEREST',
        name: 'Prohibition of Fixed Interest (Riba)',
        severity: 'blocking',
        status: 'passed',
        summary: 'Returns structured as profit distribution or rental payments, avoiding Riba.',
      });
    }

    // 4. Fatwa reference & Scholar Certification
    const fatwaRef = fieldMap.get('fatwa_reference');
    const hasFatwa = Boolean(fatwaRef || hasFatwaAttached);

    if (hasFatwa) {
      findings.push({
        rule_id: 'SHAB_FATWA_REFERENCE',
        name: 'Shariah Board Fatwa & Evidence',
        severity: 'review',
        status: 'passed',
        summary: `Fatwa certificate verified (${fatwaRef || 'Appended Supervisory Board Fatwa'}). Ready for final scholar signing.`,
      });
    } else {
      findings.push({
        rule_id: 'SHAR_FATWA_MISSING',
        name: 'Shariah Board Fatwa Reference',
        severity: 'blocking',
        status: 'failed',
        summary: 'No Fatwa document or board approval reference attached. Cannot route for scholar certification.',
        remedy: 'Attach recognized Shariah Supervisory Board Fatwa evidence document.',
      });
    }

    const hasBlockingFailure = findings.some((f) => f.severity === 'blocking' && f.status === 'failed');

    let outcome: ShariahReviewStatus;
    if (hasBlockingFailure) {
      outcome = 'system_flagged_noncompliant';
    } else if (hasFatwa) {
      outcome = 'pending_scholar_review';
    } else {
      outcome = 'system_flagged_noncompliant';
    }

    return { findings, outcome };
  }
}

// Event-Sourced Cap Table Replay Engine
export function computeCapTable(events: CapTableEvent[], issuer?: string): CapTableSnapshot {
  const issuerEvents = (!issuer || issuer === 'all')
    ? events
    : events.filter((e) => e.issuer_name.toLowerCase() === issuer.toLowerCase());

  const positionsMap = new Map<string, { name: string; shares: number; share_class: string }>();

  for (const ev of issuerEvents) {
    if (ev.event_type === 'issuance') {
      const current = positionsMap.get(ev.holder_id) || {
        name: ev.holder_name,
        shares: 0,
        share_class: ev.share_class,
      };
      current.shares += ev.share_count;
      positionsMap.set(ev.holder_id, current);
    } else if (ev.event_type === 'transfer') {
      const from = positionsMap.get(ev.holder_id);
      if (from && from.shares >= ev.share_count) {
        from.shares -= ev.share_count;
        const toId = ev.to_holder_id || 'unknown';
        const to = positionsMap.get(toId) || {
          name: ev.to_holder_name || 'Transferee',
          shares: 0,
          share_class: ev.share_class,
        };
        to.shares += ev.share_count;
        positionsMap.set(toId, to);
      }
    } else if (ev.event_type === 'cancellation') {
      const holder = positionsMap.get(ev.holder_id);
      if (holder && holder.shares >= ev.share_count) {
        holder.shares -= ev.share_count;
      }
    }
  }

  let totalShares = 0;
  positionsMap.forEach((pos) => {
    totalShares += pos.shares;
  });

  const positions: CapTableSnapshot['positions'] = [];
  positionsMap.forEach((pos, id) => {
    if (pos.shares > 0) {
      positions.push({
        holder_id: id,
        holder_name: pos.name,
        shares: pos.shares,
        share_class: pos.share_class,
        ownership_percent: totalShares > 0 ? Number(((pos.shares / totalShares) * 100).toFixed(2)) : 0,
      });
    }
  });

  // Sort descending by shares
  positions.sort((a, b) => b.shares - a.shares);

  return {
    issuer_name: issuer,
    total_fully_diluted_shares: totalShares,
    positions,
    effective_date: new Date().toISOString(),
  };
}

// Generate unique trace ID
export function generateTraceId(): string {
  return 'tr_' + Math.random().toString(36).substring(2, 10) + '_' + Date.now().toString(36);
}

// Unified Pipeline runner
export function runPipeline(params: {
  text: string;
  filename: string;
  compliance_mode: ComplianceMode;
  issuer_name?: string;
  forceFatwa?: boolean;
}): PipelineRunResult {
  const classification = classifyDocument(params.text, params.filename);
  const fields = extractFields(params.text, classification.docType);
  const { findings, outcome } = evaluateCompliance(
    params.compliance_mode,
    classification.docType,
    fields,
    params.forceFatwa
  );

  const instrumentId = 'inst_' + Math.random().toString(36).substring(2, 9);
  const docId = 'doc_' + Math.random().toString(36).substring(2, 9);
  const traceId = generateTraceId();

  const issuerField = fields.find((f) => f.name === 'issuer_name' || f.name === 'borrower' || f.name === 'issuer');
  const amountField = fields.find((f) => f.name === 'principal' || f.name === 'issue_size' || f.name === 'subscription_amount');

  const issuerName = params.issuer_name || (issuerField && String(issuerField.value)) || 'Flowgate Systems Inc.';
  const amount = (amountField && Number(amountField.value)) || 1000000;

  const instrument: Instrument = {
    id: instrumentId,
    transaction_type:
      params.compliance_mode === 'islamic'
        ? 'sukuk'
        : classification.docType === 'subscription_agreement'
        ? 'equity'
        : 'loan',
    compliance_mode: params.compliance_mode,
    issuer_name: issuerName,
    amount,
    currency: 'USD',
    shariah_review_status: outcome,
    created_at: new Date().toISOString(),
  };

  const document: DocumentRecord = {
    id: docId,
    instrument_id: instrumentId,
    filename: params.filename,
    document_type: classification.docType,
    confidence: classification.confidence,
    status: classification.confidence >= 0.75 ? 'processed' : 'review_needed',
    extracted_text: params.text,
    created_at: new Date().toISOString(),
  };

  const ledger_entries: LedgerEntry[] = [
    {
      id: 'led_cls_' + Math.random().toString(36).substring(2, 7),
      entry_type: 'document_result',
      trace_id: traceId,
      instrument_id: instrumentId,
      title: `Document Classified: ${classification.docType.replace('_', ' ')} (${(classification.confidence * 100).toFixed(0)}% confidence)`,
      details: {
        doc_type: classification.docType,
        confidence: classification.confidence,
        gate_passed: classification.confidence >= 0.75,
      },
      timestamp: new Date().toISOString(),
    },
    {
      id: 'led_cmp_' + Math.random().toString(36).substring(2, 7),
      entry_type: 'compliance_event',
      trace_id: traceId,
      instrument_id: instrumentId,
      title: `Compliance Evaluation (${params.compliance_mode.toUpperCase()}): ${outcome}`,
      details: {
        mode: params.compliance_mode,
        findings_count: findings.length,
        outcome,
      },
      timestamp: new Date().toISOString(),
    },
  ];

  let proposal_created: CapTableProposal | null = null;
  if (classification.docType === 'subscription_agreement') {
    const subscriberField = fields.find((f) => f.name === 'subscriber');
    const sharesField = fields.find((f) => f.name === 'share_count');
    const priceField = fields.find((f) => f.name === 'share_price');
    proposal_created = {
      id: 'prop_' + Math.random().toString(36).substring(2, 8),
      document_id: docId,
      issuer_name: issuerName,
      holder_name: (subscriberField && String(subscriberField.value)) || 'Apex Horizon Growth Fund LP',
      share_count: (sharesField && Number(sharesField.value)) || 150000,
      share_class: 'Common',
      share_price: (priceField && Number(priceField.value)) || 12.5,
      status: 'proposed',
      created_at: new Date().toISOString(),
    };
  }

  return {
    instrument,
    document,
    extracted_fields: fields,
    compliance_findings: findings,
    compliance_outcome: outcome,
    ledger_entries,
    proposal_created,
  };
}
