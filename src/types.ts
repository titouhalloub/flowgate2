export type ComplianceMode = 'traditional' | 'islamic';

export type TransactionType =
  | 'loan'
  | 'equity'
  | 'sukuk'
  | 'private_equity'
  | 'venture_capital'
  | 'real_asset'
  | 'fund_interest';

export type ShariahContractType = 'murabaha' | 'ijara' | 'musharakah' | 'wakalah' | 'none';

export type DocumentType =
  | 'term_sheet'
  | 'loan_agreement'
  | 'shareholder_agreement'
  | 'private_placement_memorandum'
  | 'limited_partnership_agreement'
  | 'sukuk_certificate'
  | 'fatwa'
  | 'financial_statement'
  | 'kyc'
  | 'side_letter'
  | 'safe'
  | 'subscription_agreement'
  | 'equity_subscription'
  | 'capital_call_notice'
  | 'unclassified'
  | 'other';

export type ShariahReviewStatus =
  | 'not_applicable'
  | 'system_flagged_noncompliant'
  | 'pending_scholar_review'
  | 'scholar_approved'
  | 'scholar_rejected';

export type DocumentStatus = 'uploaded' | 'processing' | 'processed' | 'review_needed' | 'failed';

export type LedgerEntryType =
  | 'category_mutation'
  | 'document_result'
  | 'compliance_event'
  | 'cap_table_event'
  | 'cap_table_proposal'
  | 'capital_call_review';

export type ProposalStatus = 'proposed' | 'approved' | 'rejected';

export type CapTableEventType = 'issuance' | 'transfer' | 'cancellation' | 'exercise' | 'conversion';

export type CapitalCallStatus =
  | 'pending_commitment_lookup'
  | 'pending_approval'
  | 'approved'
  | 'rejected';

export interface Instrument {
  id: string;
  transaction_type: TransactionType;
  compliance_mode: ComplianceMode;
  issuer_name: string;
  issuer_type?: string;
  amount: number;
  currency: string;
  maturity_date?: string | null;
  shariah_review_status?: ShariahReviewStatus;
  created_at: string;
}

export interface DocumentRecord {
  id: string;
  instrument_id: string;
  filename: string;
  document_type: DocumentType;
  confidence: number;
  status: DocumentStatus;
  extracted_text?: string;
  created_at: string;
}

export interface ExtractedField {
  name: string;
  value: string | number | null;
  confidence: number;
  evidence?: string;
}

export interface ComplianceFinding {
  rule_id: string;
  name: string;
  severity: 'blocking' | 'review' | 'advisory';
  status: 'passed' | 'failed' | 'pending';
  summary: string;
  remedy?: string;
}

export interface LedgerEntry {
  id: string;
  entry_type: LedgerEntryType;
  trace_id: string;
  instrument_id?: string;
  title: string;
  details: Record<string, any>;
  timestamp: string;
}

export interface HolderPosition {
  holder_id: string;
  holder_name: string;
  shares: number;
  share_class: string;
  ownership_percent: number;
}

export interface CapTableSnapshot {
  issuer_name: string;
  total_fully_diluted_shares: number;
  positions: HolderPosition[];
  effective_date: string;
}

export interface CapTableEvent {
  id: string;
  issuer_name: string;
  event_type: CapTableEventType;
  holder_id: string;
  holder_name: string;
  share_count: number;
  share_class: string;
  share_price?: number;
  to_holder_id?: string;
  to_holder_name?: string;
  timestamp: string;
}

export interface CapTableProposal {
  id: string;
  document_id: string;
  issuer_name: string;
  holder_name: string;
  holder_id?: string;
  share_count: number;
  share_class: string;
  share_price?: number;
  status: ProposalStatus;
  reviewer?: string;
  reviewed_at?: string;
  created_at: string;
}

export interface CapitalCall {
  id: string;
  instrument_id?: string;
  funder_name: string;
  currency: string;
  capital_owing: number;
  due_date: string | null;
  wire_details?: string;
  status: CapitalCallStatus;
  source_text?: string;
  reviewer?: string;
  reviewed_at?: string;
  created_at: string;
}

export type CapitalCallNotice = CapitalCall;

export interface Investor {
  id: string;
  name: string;
  investor_type: 'individual' | 'institution' | 'fund';
  jurisdiction: string;
  kyc_status: 'cleared' | 'pending' | 'flagged';
  created_at: string;
}

export interface PipelineRunResult {
  instrument: Instrument;
  document: DocumentRecord;
  extracted_fields: ExtractedField[];
  compliance_findings: ComplianceFinding[];
  compliance_outcome: ShariahReviewStatus;
  ledger_entries: LedgerEntry[];
  proposal_created?: CapTableProposal | null;
}
