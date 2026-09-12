import {
  CapTableEvent,
  CapTableProposal,
  CapitalCall,
  CapitalCallStatus,
  Investor,
  LedgerEntry,
  ProposalStatus,
} from '../types';

// ---------------------------------------------------------------------------
// Connection state -- shared by every live handler. When apiBase points at the
// Python FastAPI backend (local or Render) every handler goes live-first and
// falls back to the local demo mutation only if the API call fails.
// ---------------------------------------------------------------------------
let apiBase = '';
let apiKey = 'development_key_123';
let cachedInstrumentId: string | null = null;

export function configureApi(base: string, key: string): void {
  apiBase = base;
  apiKey = key;
  cachedInstrumentId = null;
}

export function getApiBase(): string {
  return apiBase;
}

export function isLive(): boolean {
  return apiBase.length > 0;
}

export function authHeaders(json = true): Record<string, string> {
  const headers: Record<string, string> = {};
  if (json) headers['Content-Type'] = 'application/json';
  if (apiKey) headers['X-API-Key'] = apiKey;
  return headers;
}

function cleanBase(): string {
  return apiBase.replace(/\/$/, '');
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(`${cleanBase()}${path}`, {
    ...init,
    headers: { ...authHeaders(!isForm), ...(init.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as Record<string, string>).detail ||
        `Request failed (${res.status}): ${path}`
    );
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Mappers: backend DTO shapes -> frontend types
// ---------------------------------------------------------------------------

export function mapInvestor(row: Record<string, unknown>): Investor {
  return {
    id: row.id as string,
    name: row.name as string,
    investor_type: ((row.investor_type as string) ||
      'individual') as Investor['investor_type'],
    jurisdiction: (row.jurisdiction as string) || 'Global',
    kyc_status: row.kyc_verified ? 'cleared' : 'pending',
    created_at: (row.created_at as string) || new Date().toISOString(),
  };
}

export function mapCapitalCall(row: Record<string, unknown>): CapitalCall {
  return {
    id: row.id as string,
    instrument_id: row.instrument_id as string,
    funder_name:
      (row.funder_name as string) ||
      (row.funder_id as string) ||
      'Unresolved funder',
    currency: (row.currency as string) || 'USD',
    capital_owing: (row.capital_owing as number) ?? (row.amount_due as number) ?? 0,
    due_date: (row.due_date as string) || null,
    wire_details: (row.wire_details as string) || undefined,
    status: ((row.status as string) || 'pending_approval') as CapitalCallStatus,
    source_text: (row.source_text as string) || undefined,
    created_at: (row.created_at as string) || new Date().toISOString(),
    payment_status: (row.payment_status as CapitalCall['payment_status']) || undefined,
    remaining: typeof row.remaining === 'number' ? row.remaining : undefined,
  };
}

export function mapProposal(row: Record<string, unknown>): CapTableProposal {
  const payload = (row.payload as Record<string, unknown>) || {};
  return {
    id: row.id as string,
    document_id: row.document_id as string,
    issuer_name: (payload.issuer_name as string) || 'Unknown issuer',
    holder_name: (payload.holder_name as string) || 'Unlinked holder',
    holder_id: (payload.holder_id as string) || undefined,
    share_count: (payload.share_count as number) ?? 0,
    share_class: (payload.security_name as string) || 'Common',
    share_price: (payload.price_per_share as number) ?? undefined,
    status: ((row.status as string) || 'proposed') as ProposalStatus,
    created_at: (row.created_at as string) || new Date().toISOString(),
  };
}

export function mapLedgerEntry(row: Record<string, unknown>): LedgerEntry {
  return {
    id: row.id as string,
    entry_type: ((row.entry_type as string) ||
      'document_result') as LedgerEntry['entry_type'],
    trace_id: (row.trace_id as string) || (row.id as string),
    instrument_id: row.instrument_id as string | undefined,
    title:
      (row.title as string) ||
      String(row.entry_type || 'event').replace(/_/g, ' '),
    details:
      (row.details as Record<string, unknown>) ||
      (row.payload as Record<string, unknown>) ||
      {},
    timestamp:
      (row.timestamp as string) ||
      (row.created_at as string) ||
      new Date().toISOString(),
  };
}

export function mapCapTableEvent(row: Record<string, unknown>): CapTableEvent {
  // POST /cap-table-events returns a CapTableEventOut (security-centric).
  // The frontend event model is issuer/holder-centric; issuer_name is filled
  // in by the caller that knows the issuer context.
  return {
    id: row.id as string,
    issuer_name: (row.issuer_name as string) || '',
    event_type: (row.event_type as CapTableEvent['event_type']) || 'issuance',
    holder_id: (row.holder_id as string) || '',
    holder_name: (row.holder_name as string) || (row.holder_id as string) || '',
    share_count: (row.quantity as number) ?? 0,
    share_class: (row.share_class as string) || 'Common',
    share_price: (row.price_per_share as number) ?? undefined,
    timestamp: (row.effective_date as string) || new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Endpoint wrappers (each throws on failure so callers can fall back to demo)
// ---------------------------------------------------------------------------

export async function checkHealth(): Promise<boolean> {
  try {
    const data = await request<{ status: string }>('/health');
    return data.status === 'ok';
  } catch {
    return false;
  }
}

export async function listInvestors(): Promise<Investor[]> {
  const rows = await request<Array<Record<string, unknown>>>('/investors');
  return rows.map(mapInvestor);
}

export async function createInvestor(
  name: string,
  investorType: string
): Promise<Investor> {
  const row = await request<Record<string, unknown>>('/investors', {
    method: 'POST',
    body: JSON.stringify({ name, investor_type: investorType }),
  });
  return mapInvestor(row);
}

export async function listCapitalCalls(): Promise<CapitalCall[]> {
  const rows = await request<Array<Record<string, unknown>>>('/capital-calls');
  return rows.map(mapCapitalCall);
}

export async function listOverdueCapitalCalls(): Promise<CapitalCall[]> {
  const rows = await request<Array<Record<string, unknown>>>(
    '/capital-calls/overdue'
  );
  return rows.map(mapCapitalCall);
}

export async function reviewCapitalCall(
  callId: string,
  reviewer: string,
  action: 'approve' | 'reject'
): Promise<CapitalCall> {
  const row = await request<Record<string, unknown>>(
    `/capital-calls/${callId}/review`,
    { method: 'POST', body: JSON.stringify({ reviewer, action }) }
  );
  return mapCapitalCall(row);
}

// ---------------------------------------------------------------------------
// Phase C reconciliation -- payments against approved capital calls
// ---------------------------------------------------------------------------

export async function listCapitalCallPayments(
  callId: string
): Promise<CapitalCallPayment[]> {
  const rows = await request<Array<Record<string, unknown>>>(
    `/capital-calls/${callId}/payments`
  );
  return rows.map(
    (row) =>
      ({
        id: row.id as string,
        capital_call_id: row.capital_call_id as string,
        amount: row.amount as number,
        currency: (row.currency as string) || 'USD',
        paid_date: (row.paid_date as string) || new Date().toISOString(),
        reference: (row.reference as string) || null,
        recorded_by: (row.recorded_by as string) || 'unknown',
        created_at: (row.created_at as string) || new Date().toISOString(),
      }) as CapitalCallPayment
  );
}

export async function recordCapitalCallPayment(
  callId: string,
  body: {
    amount: number;
    currency: string;
    paid_date?: string;
    reference?: string;
    recorded_by: string;
  }
): Promise<CapitalCallPayment> {
  const row = await request<Record<string, unknown>>(
    `/capital-calls/${callId}/payments`,
    { method: 'POST', body: JSON.stringify(body) }
  );
  return {
    id: row.id as string,
    capital_call_id: row.capital_call_id as string,
    amount: row.amount as number,
    currency: (row.currency as string) || 'USD',
    paid_date: (row.paid_date as string) || new Date().toISOString(),
    reference: (row.reference as string) || null,
    recorded_by: (row.recorded_by as string) || 'unknown',
    created_at: (row.created_at as string) || new Date().toISOString(),
  } as CapitalCallPayment;
}

export async function listProposals(): Promise<CapTableProposal[]> {
  const rows = await request<Array<Record<string, unknown>>>(
    '/cap-table-proposals'
  );
  return rows.map(mapProposal);
}

export async function approveProposal(
  proposalId: string,
  reviewer: string
): Promise<CapTableProposal> {
  const row = await request<Record<string, unknown>>(
    `/cap-table-proposals/${proposalId}/approve?reviewer=${encodeURIComponent(reviewer)}`,
    { method: 'POST' }
  );
  return mapProposal(row);
}

export async function rejectProposal(
  proposalId: string,
  reviewer: string
): Promise<CapTableProposal> {
  const row = await request<Record<string, unknown>>(
    `/cap-table-proposals/${proposalId}/reject?reviewer=${encodeURIComponent(reviewer)}`,
    { method: 'POST' }
  );
  return mapProposal(row);
}

export async function linkInvestor(
  proposalId: string,
  investorId: string,
  reviewer: string
): Promise<CapTableProposal> {
  const row = await request<Record<string, unknown>>(
    `/cap-table-proposals/${proposalId}/link-investor?investor_id=${encodeURIComponent(investorId)}&reviewer=${encodeURIComponent(reviewer)}`,
    { method: 'POST' }
  );
  return mapProposal(row);
}

// Capital calls are instrument-scoped on the backend and there is no list
// endpoint, so we create (and cache) one demo container per session.
export async function ensureInstrument(): Promise<string> {
  if (cachedInstrumentId) return cachedInstrumentId;
  const inst = await request<Record<string, unknown>>('/instruments', {
    method: 'POST',
    body: JSON.stringify({
      transaction_type: 'fund_interest',
      compliance_mode: 'traditional',
      issuer_name: 'Flowgate Demo Fund',
      issuer_type: 'Fund',
      amount: 10000000,
      currency: 'USD',
    }),
  });
  cachedInstrumentId = inst.id as string;
  return cachedInstrumentId;
}

export async function createCapitalCall(body: {
  funder_name: string;
  currency: string;
  capital_owing: number;
  due_date?: string | null;
  wire_details?: string | null;
}): Promise<CapitalCall> {
  const instrumentId = await ensureInstrument();
  const row = await request<Record<string, unknown>>(
    `/instruments/${instrumentId}/capital-calls`,
    { method: 'POST', body: JSON.stringify(body) }
  );
  return mapCapitalCall(row);
}

export async function createSecurity(body: {
  issuer_name: string;
  name: string;
  security_type: string;
  authorized_shares: number;
}): Promise<string> {
  const row = await request<Record<string, unknown>>('/securities', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return row.id as string;
}

export async function createCapTableEvent(body: {
  security_id: string;
  event_type: string;
  holder_id?: string | null;
  from_holder_id?: string | null;
  quantity: number;
  price_per_share?: number | null;
  effective_date: string;
  notes?: string | null;
}): Promise<CapTableEvent> {
  const row = await request<Record<string, unknown>>('/cap-table-events', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return mapCapTableEvent(row);
}

export async function instrumentLedger(
  instrumentId: string
): Promise<LedgerEntry[]> {
  const rows = await request<Array<Record<string, unknown>>>(
    `/instruments/${instrumentId}/ledger`
  );
  return rows.map(mapLedgerEntry);
}

// ---------------------------------------------------------------------------
// Entity resolution helpers -- resolve names to registry ids before writing
// cap-table events (the backend FKs require real securities/investors).
// ---------------------------------------------------------------------------
const securityIdCache = new Map<string, string>();
const holderIdCache = new Map<string, string>();

export async function ensureSecurity(
  issuerName: string,
  shareClass: string
): Promise<string> {
  const key = `${issuerName}|${shareClass}`;
  const cached = securityIdCache.get(key);
  if (cached) return cached;
  const securityType = shareClass.toLowerCase().includes('pref')
    ? 'preferred'
    : 'common';
  const id = await createSecurity({
    issuer_name: issuerName,
    name: shareClass,
    security_type: securityType,
    authorized_shares: 10000000,
  });
  securityIdCache.set(key, id);
  return id;
}

export async function ensureHolder(
  holderName: string,
  investorType: Investor['investor_type'] = 'individual'
): Promise<string> {
  const cached = holderIdCache.get(holderName);
  if (cached) return cached;
  const existing = await listInvestors();
  const match = existing.find(
    (i) => i.name.toLowerCase() === holderName.toLowerCase()
  );
  if (match) {
    holderIdCache.set(holderName, match.id);
    return match.id;
  }
  const created = await createInvestor(holderName, investorType);
  holderIdCache.set(holderName, created.id);
  return created.id;
}
