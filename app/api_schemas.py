"""API-layer request/response schemas -- separate from the extraction schemas in
app/schemas.py, which model document data, not HTTP payloads."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    CapitalCallStatus,
    ComplianceMode,
    DocumentType,
    ShariahContractType,
    ShariahReviewStatus,
    TransactionType,
)


class InstrumentCreate(BaseModel):
    transaction_type: TransactionType
    compliance_mode: ComplianceMode
    issuer_name: str
    issuer_type: str = Field(..., description="Corporate, SPV, Fund, Government")
    amount: float
    currency: str = Field(min_length=3, max_length=8)
    maturity_date: datetime | None = None


class InstrumentOut(BaseModel):
    id: str
    transaction_type: TransactionType
    compliance_mode: ComplianceMode
    issuer_name: str
    amount: float
    currency: str
    shariah_contract_type: ShariahContractType | None
    shariah_review_status: ShariahReviewStatus
    underlying_asset_description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentSubmit(BaseModel):
    """MVP intake: raw text, not a file upload -- OCR/file handling is a
    separate, already-built concern (app/ocr.py) this endpoint can grow into
    without changing its shape."""
    text: str = Field(..., min_length=1)
    filename: str = "document.txt"


class EvidenceDocumentSubmit(BaseModel):
    """For supporting/evidence documents (fatwas, KYC, side letters) that the
    compliance gateway needs *attached and typed*, not extracted -- there is
    no LoanExtraction-style schema for a fatwa, and there shouldn't be one.
    """
    text: str = Field(..., min_length=1)
    document_type: DocumentType
    filename: str = "evidence.txt"


class DocumentOut(BaseModel):
    id: str
    instrument_id: str
    filename: str
    file_url: str | None = None
    document_type: DocumentType
    classification_confidence: float
    extraction_confidence: float
    extraction_schema_name: str | None = None
    ingestion_source: str
    status: str
    shariah_review_status: ShariahReviewStatus
    error_message: str | None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunOut(BaseModel):
    document: DocumentOut
    instrument: InstrumentOut
    outcome: ShariahReviewStatus
    routed_to_review: bool


class PipelineUploadOut(PipelineRunOut):
    """PipelineRunOut plus the text the system actually read from the
    uploaded file -- transparency about what was parsed, and it lets the
    client re-run review flows (attach-fatwa-and-recheck) without
    re-uploading."""

    extracted_text: str
    # What the parser actually read from the PDF (after the MAX_PDF_PAGES /
    # MAX_PDF_CHARS caps in app.ocr) -- transparency about bounded intake.
    # None for non-PDF uploads.
    pages_read: int | None = None
    pages_total: int | None = None


class HumanReviewRequest(BaseModel):
    reviewer_id: str = Field(..., min_length=1)
    decision: str = Field(..., pattern="^(approved|rejected)$")
    notes: str = ""


class LedgerEntryOut(BaseModel):
    id: str
    entry_type: str
    instrument_id: str | None
    document_id: str | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorOut(BaseModel):
    detail: str


# --------------------------------------------------------------------------- #
# Cap table schemas -- the live cap-table demo panel
# --------------------------------------------------------------------------- #


class InvestorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    investor_type: str = Field(..., pattern="^(individual|institution|fund)$")


class InvestorOut(BaseModel):
    id: str
    name: str
    investor_type: str
    kyc_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class HoldingCreate(BaseModel):
    investor_id: str
    stake_amount: float = Field(gt=0)
    ownership_percentage: float | None = Field(default=None, ge=0, le=100)


class HoldingOut(BaseModel):
    id: str
    investor_id: str
    instrument_id: str
    stake_amount: float
    ownership_percentage: float | None
    status: str
    acquired_at: datetime

    model_config = {"from_attributes": True}


class PortfolioHoldingOut(BaseModel):
    """One row in a cross-fund portfolio view -- the holding plus enough of
    the underlying instrument to be useful without a second round trip."""

    holding: HoldingOut
    instrument: InstrumentOut


class InvestorPortfolioOut(BaseModel):
    investor: InvestorOut
    holdings: list[PortfolioHoldingOut]
    total_traditional_exposure: float
    total_islamic_exposure: float
    fund_count: int


class SecurityCreate(BaseModel):
    issuer_name: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    security_type: str = Field(
        ..., pattern="^(common|preferred|option|warrant|safe|convertible_note)$"
    )
    authorized_shares: float = Field(gt=0)
    par_value: float | None = Field(default=None, ge=0)


class SecurityOut(BaseModel):
    id: str
    issuer_name: str
    name: str
    security_type: str
    authorized_shares: float
    par_value: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GrantVestingOut(BaseModel):
    event_id: str
    security_id: str
    holder_id: str
    original_shares: float
    total_shares: float
    vested_shares: float
    unvested_shares: float
    transferred_vested_shares: float
    repurchased_vested_shares: float
    vesting_start_date: date
    vesting_period_months: int
    cliff_months: int
    cliff_date: date | None = None
    fully_vested_date: date | None = None
    is_fully_vested: bool
    acceleration_clause: str | None = None

    model_config = {"from_attributes": True}


class CapTableEventCreate(BaseModel):
    security_id: str
    target_security_id: str | None = None
    event_type: str = Field(
        ..., pattern="^(issuance|transfer|cancellation|exercise|conversion)$"
    )
    holder_id: str | None = None
    from_holder_id: str | None = None
    quantity: float = Field(gt=0)
    price_per_share: float | None = Field(default=None, ge=0)
    effective_date: datetime
    notes: str | None = None
    vesting_start_date: date | None = None
    vesting_period_months: int | None = Field(default=None, gt=0)
    cliff_months: int | None = Field(default=None, ge=0)
    acceleration_clause: str | None = Field(default=None, pattern="^(none|single_trigger|double_trigger)$")
    is_repurchase: bool = False
    repurchase_approver: str | None = None

    @model_validator(mode="after")
    def validate_vesting_and_repurchase(self) -> CapTableEventCreate:
        if self.cliff_months is not None and self.vesting_period_months is not None:
            if self.cliff_months > self.vesting_period_months:
                raise ValueError("cliff_months cannot exceed vesting_period_months")
        if self.is_repurchase:
            if not self.repurchase_approver or not self.repurchase_approver.strip():
                raise ValueError("repurchase_approver is required when is_repurchase is True")
            self.repurchase_approver = self.repurchase_approver.strip()
        return self


class CapTableEventOut(BaseModel):
    id: str
    security_id: str
    target_security_id: str | None
    event_type: str
    holder_id: str | None
    from_holder_id: str | None
    quantity: float
    price_per_share: float | None
    effective_date: datetime
    notes: str | None
    vesting_start_date: date | None = None
    vesting_period_months: int | None = None
    cliff_months: int | None = None
    acceleration_clause: str | None = None
    is_repurchase: bool = False
    repurchase_approver: str | None = None

    model_config = {"from_attributes": True}


class HolderPositionOut(BaseModel):
    holder_id: str
    holder_name: str
    security_id: str
    security_name: str
    shares: float
    vested_shares: float = 0.0
    unvested_shares: float = 0.0
    # This POSITION's share of the fully-diluted total -- NOT the holder's
    # overall percentage. The holder's total across all their securities is
    # reported once, explicitly, in CapTableOut.ownership_by_holder.
    # Repeating the holder total on every row made clients double-count.
    ownership_percent: float


class CapTableProposalOut(BaseModel):
    """A prepared (inert) cap-table issuance from a processed document."""

    id: str
    document_id: str
    instrument_id: str | None = None
    proposal_type: str
    status: str
    payload: dict[str, Any]
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CapTableOut(BaseModel):
    issuer_name: str
    as_of: datetime
    total_fully_diluted_shares: float
    total_vested_shares: float = 0.0
    total_unvested_shares: float = 0.0
    shares_by_security: dict[str, float]
    ownership_by_holder: dict[str, float]
    positions: list[HolderPositionOut]
    grants: list[GrantVestingOut] = []


# --------------------------------------------------------------------------- #
# Capital call schemas -- Phase A approval parity
# --------------------------------------------------------------------------- #


class CapitalCallCreate(BaseModel):
    """Request body for creating a capital call notice from an extracted
    document. Mirrors the fields on CapitalCallExtraction."""
    funder_name: str = Field(..., min_length=1)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    capital_owing: float = Field(gt=0)
    due_date: datetime | None = None
    wire_details: str | None = None
    source_text: str | None = None


class CapitalCallOut(BaseModel):
    """Read-side view of a CapitalCall, used by the review queue."""
    id: str
    instrument_id: str
    funder_id: str | None
    # Resolved from the Investor registry at READ time (never stored on the
    # call row -- the FK is the source of truth). Lets any client show who
    # owes without shipping the whole registry to the browser.
    funder_name: str | None = None
    capital_owing: float
    committed_capital: float | None
    amount_due: float
    currency: str
    due_date: datetime | None
    wire_details: str | None
    source_text: str
    pages_read: int | None
    pages_total: int | None
    confidence: float
    status: str
    requires_manual_review: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Phase C reconciliation -- DERIVED at read time from sum(payments) vs
    # amount_due, never stored. ``payment_status`` is unpaid/partial/paid;
    # ``remaining`` = max(0, amount_due - total_paid) so the UI never
    # recomputes it differently from the server.
    total_paid: float = 0.0
    remaining: float = 0.0
    payment_status: str = "unpaid"

    model_config = {"from_attributes": True}


class CapitalCallReviewRequest(BaseModel):
    """Request body for the capital-call approval gate (Phase A)."""
    reviewer: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^(approve|reject)$")


class PaymentCreate(BaseModel):
    """Request body for recording a payment against an APPROVED capital
    call (Phase C). ``recorded_by`` is a named human -- same audit rule as
    every other gate; the endpoint refuses anonymous receipts."""

    amount: float = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    paid_date: datetime
    reference: str | None = Field(default=None, max_length=255)
    recorded_by: str = Field(..., min_length=1)


class PaymentOut(BaseModel):
    """Read-side view of a recorded CapitalCallPayment."""

    id: str
    capital_call_id: str
    amount: float
    currency: str
    paid_date: datetime
    reference: str | None = None
    recorded_by: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------- #
# Transfer rules / ROFR engine -- Phase D governance gate
# --------------------------------------------------------------------------- #


class TransferRuleCreate(BaseModel):
    """Request body for creating a governance rule scoped to an issuer.

    ``condition`` is a typed JSON bag keyed by ``rule_type`` (validated by
    app.transfer_rules.validate_rule_condition -- unknown keys ride along
    verbatim so future rule types never need a migration)."""

    issuer_name: str = Field(..., min_length=1, max_length=255)
    # No pattern here ON PURPOSE: an unknown rule_type must surface as the
    # endpoint's 400 (from validate_rule_condition), not Pydantic's 422.
    rule_type: str = Field(..., min_length=1, max_length=64)
    condition: dict[str, Any] = Field(default_factory=dict)
    # Top-level ROFR-window field, merged into ``condition`` by the endpoint
    # before validation; must be a positive int when present (400, not 422).
    window_days: int | None = None
    gate: str = Field(..., pattern="^(block|review)$")
    approver: str = Field(..., min_length=1, max_length=255)
    escalation_role: str | None = Field(default=None, max_length=255)
    escalation_after_days: int | None = Field(default=None, ge=1)
    created_by: str = Field(..., min_length=1, max_length=64)


class TransferRuleOut(BaseModel):
    """Read-side view of a TransferRule (active and inactive both)."""

    id: str
    issuer_name: str
    rule_type: str
    condition: dict[str, Any]
    gate: str
    approver: str
    escalation_role: str | None = None
    escalation_after_days: int | None = None
    active: bool
    created_by: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TransferEvaluationOut(BaseModel):
    """Read-side view of one gate decision. ``overdue`` is *derived* at
    read time (pending AND older than the rule's escalation_after_days) --
    the same derivation-only pattern as the Phase B overdue badge; it is
    never stored."""

    id: str
    security_id: str
    from_holder_id: str
    holder_id: str
    quantity: float
    price_per_share: float | None = None
    effective_date: datetime
    rules_evaluated: list[dict[str, Any]] = []
    outcome: str
    blocking_rule_id: str | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None
    overdue: bool = False

    model_config = {"from_attributes": True}


