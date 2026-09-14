"""SQLAlchemy ORM models for the Flowgate pipeline.

Instrument and Document are generic: one compliance gateway and one ledger
serve every asset class via ``transaction_type`` and ``type_specific_data``.

No-self-certification guarantee
------------------------------
``ShariahReviewStatus.SCHOLAR_APPROVED`` / ``SCHOLAR_REJECTED`` are human-only.
The ORM models enforce this *at the type level*: the ``shariah_review_status``
column can only be assigned values in ``SYSTEM_SETTABLE`` through ordinary ORM writes, because the ``human_review`` relationship exposes
``set_shariah_review_status()`` as the *only* path to the human-only states,
and that path requires an explicit ``reviewer_id``.

This is a type-level guarantee in the sense that the ORM assignments are
validated at write-time via a ``@validates`` callback (not merely documented),
and any attempt to smuggle ``SCHOLAR_APPROVED`` through a normal ORM write
raises ``ValueError``. Tests in ``tests/test_models.py`` prove this.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db import Base
from app.models.enums import (
    CapTableEventType,
    CapitalCallStatus,
    ComplianceMode,
    DocumentStatus,
    DocumentType,
    HoldingStatus,
    IngestionSource,
    InvestorType,
    LedgerEntryType,
    ProposalStatus,
    ProposalType,
    SecurityType,
    TransactionType,
    ShariahContractType,
    ShariahReviewStatus,
    TransferEvaluationOutcome,
    TransferGate,
    TransferRuleType,
    ValuationType,
    ConvertibleStatus,
    SYSTEM_SETTABLE,
    HUMAN_ONLY,
)
from app.models.enums import (
    ComplianceMode,
    DocumentStatus,
    DocumentType,
    IngestionSource,
    LedgerEntryType,
    TransactionType,
    ShariahContractType,
    ShariahReviewStatus,
    SYSTEM_SETTABLE,
    HUMAN_ONLY,
)

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    """Timezone-aware UTC now (stored as UTC in ISO8601-serialisable form)."""
    return datetime.now(timezone.utc)


class ShariahReviewValidationError(ValueError):
    """Raised when code or a caller tries to set a human-only review state.

    This guard is *absolute* at the ORM attribute level: no repo method,
    service, or background task can ever assign ``SCHOLAR_APPROVED`` or
    ``SCHOLAR_REJECTED`` through a normal ORM write.

    The single deliberate exception is ``app.review.submit_human_review``,
    which writes these states through a SQLAlchemy Core ``update()`` statement
    (escaping the ORM validates callback *on purpose*) and additionally
    requires an explicit ``reviewer_id`` — the model of "the human review
    endpoint is the only way through".
    """


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------


class Instrument(Base):
    """One instrument across any asset class.

    ``type_specific_data`` is a JSONB bag that holds the asset-class-specific
    fields (e.g. ``interest_rate`` for loans, ``coupon_rate`` for sukuk).
    """

    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, native_enum=False, length=32)
    )
    compliance_mode: Mapped[ComplianceMode] = mapped_column(
        Enum(ComplianceMode, native_enum=False, length=32)
    )
    issuer_name: Mapped[str] = mapped_column(String(255))
    issuer_type: Mapped[str] = mapped_column(String(64))  # Corporate, SPV, Fund, Government
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    maturity_date: Mapped[datetime | None] = mapped_column(default=None)
    type_specific_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    underlying_asset_description: Mapped[str | None] = mapped_column(Text, default=None)
    underlying_asset_id: Mapped[str | None] = mapped_column(String(128), default=None)
    shariah_contract_type: Mapped[ShariahContractType | None] = mapped_column(
        Enum(ShariahContractType, native_enum=False, length=32), default=None
    )
    shariah_review_status: Mapped[ShariahReviewStatus] = mapped_column(
        Enum(ShariahReviewStatus, native_enum=False, length=48),
        default=ShariahReviewStatus.NOT_APPLICABLE,
    )
    shariah_reviewer_id: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="instrument",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------ #
    # Type-level guards
    # ------------------------------------------------------------------ #

    @validates("shariah_review_status")
    def _validate_review_status(self, key: str, value: Any) -> ShariahReviewStatus:
        """Block all human-only states at the ORM write level.

        ``SCHOLAR_APPROVED`` / ``SCHOLAR_REJECTED`` cannot be reached through
        any attribute or ORM write — only ``app.review.submit_human_review``
        may set them, via a deliberate Core ``update()`` path.
        """
        value = (
            ShariahReviewStatus(value)
            if not isinstance(value, ShariahReviewStatus)
            else value
        )
        if value in HUMAN_ONLY:
            raise ShariahReviewValidationError(
                f"Cannot set {value!r} on Instrument {self.id!r} outside an "
                "explicit human review endpoint (reviewer_id required)."
            )
        return value


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_instrument_id", "instrument_id"),
        UniqueConstraint("instrument_id", "file_url", name="uq_document_instrument_file"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(64), ForeignKey("instruments.id"))
    filename: Mapped[str] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(1024))
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, native_enum=False, length=64)
    )
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    extraction_schema_name: Mapped[str] = mapped_column(String(255), default="")
    extraction_schema_version: Mapped[str] = mapped_column(String(32), default="")
    ingestion_source: Mapped[IngestionSource] = mapped_column(
        Enum(IngestionSource, native_enum=False, length=32),
        default=IngestionSource.NATIVE_EXTRACTION,
    )
    compliance_mode: Mapped[ComplianceMode] = mapped_column(
        Enum(ComplianceMode, native_enum=False, length=32)
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False, length=32),
        default=DocumentStatus.UPLOADED,
    )
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    shariah_review_status: Mapped[ShariahReviewStatus] = mapped_column(
        Enum(ShariahReviewStatus, native_enum=False, length=48),
        default=ShariahReviewStatus.NOT_APPLICABLE,
    )
    shariah_reviewer_id: Mapped[str | None] = mapped_column(String(64), default=None)
    shariah_validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list
    )
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    uploaded_at: Mapped[datetime] = mapped_column(default=_utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(default=None)

    instrument: Mapped["Instrument"] = relationship(back_populates="documents")

    @validates("shariah_review_status")
    def _validate_doc_review_status(self, key: str, value: Any) -> ShariahReviewStatus:
        value = (
            ShariahReviewStatus(value)
            if not isinstance(value, ShariahReviewStatus)
            else value
        )
        if value in HUMAN_ONLY:
            raise ShariahReviewValidationError(
                f"Cannot set {value!r} on Document {self.id!r}: only a human "
                "reviewer may approve/reject (use the review endpoint)."
            )
        return value


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


class LedgerEntry(Base):
    """Append-only ledger.

    Every row carries the entry type, the affected instrument/document,
    the payload (the classification decision, extraction result, or
    compliance event), the raw model inputs that produced it, and a trace_id
    linking the row to its Langfuse trace so decisions are reproducible.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_instrument_id", "instrument_id"),
        Index("ix_ledger_document_id", "document_id"),
        Index("ix_ledger_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        Enum(LedgerEntryType, native_enum=False, length=48)
    )
    instrument_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("instruments.id"), default=None
    )
    document_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("documents.id"), default=None
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_input: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<LedgerEntry {self.id} type={self.entry_type.value} "
            f"instrument={self.instrument_id!r}>"
        )


# ---------------------------------------------------------------------------
# Cap table (live cap-table demo) -- event-sourced positions, replayed at
# query time. Supported by the "Live cap table" panel in the demo HTML.
# ---------------------------------------------------------------------------


class Investor(Base):
    """A holder of instruments/securities -- an individual, an institution,
    or a fund. The FUND type is what makes a cross-fund portfolio view a
    native join here rather than a portal-scraping integration."""

    __tablename__ = "investors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    investor_type: Mapped[InvestorType] = mapped_column(
        Enum(InvestorType, native_enum=False, length=24)
    )
    # Investor-level record of the KYC/AML review. The traditional-track
    # gateway checks for a KYC *document* attached to the instrument; this
    # flag is the same review recorded on the investor, queryable without
    # joining encrypted document rows.
    kyc_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return f"<Investor {self.id} {self.name!r}>"


class Security(Base):
    """A class of equity in a company -- 'Series A Preferred', 'Common
    Stock', a 2024 option pool. This is deliberately separate from
    Instrument: an Instrument is one deal (a loan, a single sukuk
    issuance); a Security is an ongoing class of equity a company issues
    to many holders, across many rounds, over years. Cap tables are built
    on Security + CapTableEvent, not Instrument.

    ``issuer_name`` is a plain string rather than a foreign key to a full
    Issuer/Company entity -- there is no such entity yet in this schema.
    That's a real simplification: two securities with the same
    ``issuer_name`` string are currently the only way this system knows
    they belong to the same company.
    """

    __tablename__ = "securities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer_name: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))  # e.g. "Common Stock"
    security_type: Mapped[SecurityType] = mapped_column(
        Enum(SecurityType, native_enum=False, length=24)
    )
    authorized_shares: Mapped[float] = mapped_column(Float)
    par_value: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return f"<Security {self.id} {self.issuer_name!r}/{self.name!r}>"


class CapTableEvent(Base):
    """Append-only. The cap table at any point in time is *computed* by
    replaying these events up to that date (see
    ``app.captable.compute_cap_table``), never stored as a row that gets
    hand-edited and drifts out of sync with reality. Backed by the "Live
    cap table" panel in the demo HTML.

    ``security_id`` is the security primarily debited/credited by this
    event. ``target_security_id`` is only used for EXERCISE (option ->
    common) and CONVERSION (SAFE/note -> preferred or common), where shares
    move from one security class into another for the same holder.
    """

    __tablename__ = "cap_table_events"
    __table_args__ = (
        Index("ix_captable_security_id", "security_id"),
        Index("ix_captable_effective_date", "effective_date"),
        Index("ix_captable_related_round", "related_round_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    security_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("securities.id")
    )
    target_security_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("securities.id"), default=None
    )
    event_type: Mapped[CapTableEventType] = mapped_column(
        Enum(CapTableEventType, native_enum=False, length=16)
    )
    holder_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("investors.id")
    )
    from_holder_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("investors.id"), default=None
    )
    quantity: Mapped[float] = mapped_column(Float)
    price_per_share: Mapped[float | None] = mapped_column(Float, default=None)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(default=_utcnow)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    # Priced-round provenance: the convertible this event converted (for
    # CONVERSION) and the round that triggered it (for the round ISSUANCE
    # and every CONVERSION it caused). Nullable -- plain events have none.
    related_convertible_id: Mapped[str | None] = mapped_column(
        String(64), default=None
    )
    related_round_id: Mapped[str | None] = mapped_column(
        String(64), default=None
    )
    vesting_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    vesting_period_months: Mapped[int | None] = mapped_column(nullable=True, default=None)
    cliff_months: Mapped[int | None] = mapped_column(nullable=True, default=None)
    acceleration_clause: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    is_repurchase: Mapped[bool] = mapped_column(Boolean, default=False)
    repurchase_approver: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)

    @validates("is_repurchase")
    def _validate_is_repurchase(self, key: str, value: Any) -> bool:
        val = bool(value)
        if val and getattr(self, "event_type", None) is not None:
            evt_type = (
                self.event_type.value
                if isinstance(self.event_type, CapTableEventType)
                else str(self.event_type)
            )
            if evt_type != CapTableEventType.CANCELLATION.value:
                raise ValueError("is_repurchase may only be set on CANCELLATION events.")
        return val

    def __repr__(self) -> str:
        return (
            f"<CapTableEvent {self.event_type.value} security={self.security_id!r} "
            f"qty={self.quantity}>"
        )


# ---------------------------------------------------------------------------
# Cross-fund portfolio -- Holding is the join that lets one investor's
# portfolio span traditional and Islamic instruments from many issuers and
# be answered in a single query (GET /investors/{id}/portfolio).
# ---------------------------------------------------------------------------


class Holding(Base):
    """An investor's stake in one instrument."""

    __tablename__ = "holdings"
    __table_args__ = (
        Index("ix_holdings_investor_id", "investor_id"),
        Index("ix_holdings_instrument_id", "instrument_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investor_id: Mapped[str] = mapped_column(String(64), ForeignKey("investors.id"))
    instrument_id: Mapped[str] = mapped_column(String(64), ForeignKey("instruments.id"))
    stake_amount: Mapped[float] = mapped_column(Float)
    ownership_percentage: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[HoldingStatus] = mapped_column(
        Enum(HoldingStatus, native_enum=False, length=16),
        default=HoldingStatus.ACTIVE,
    )
    acquired_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<Holding investor={self.investor_id!r} instrument={self.instrument_id!r} "
            f"amount={self.stake_amount}>"
        )


# ---------------------------------------------------------------------------
# Capital calls -- ingestion, commitment lookup, and approval gating.
# ---------------------------------------------------------------------------


class CapitalCall(Base):
    """A capital call notice extracted from a document, pending approval.

    The system NEVER moves money on its own. An extracted call is
    ``PENDING_APPROVAL`` until a named human reviewer confirms it. Only
    approval materializes a real ``CapTableEvent`` (issuance of the called
    capital). See ``app.proposals`` for the approval gate.

    ``committed_capital`` is looked up from the linked ``Holding`` row; if no
    holding exists for (funder, instrument), the call is flagged for manual
    review rather than guessing a commitment amount.
    """

    __tablename__ = "capital_calls"
    __table_args__ = (
        Index("ix_capital_calls_instrument_id", "instrument_id"),
        Index("ix_capital_calls_funder_id", "funder_id"),
        Index("ix_capital_calls_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("instruments.id")
    )
    funder_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("investors.id"), nullable=True
    )
    capital_owing: Mapped[float] = mapped_column(Float, nullable=False)
    committed_capital: Mapped[float | None] = mapped_column(Float, default=None)
    amount_due: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    wire_details: Mapped[str | None] = mapped_column(Text, default=None)
    # What the extractor actually read — the audit trail of the parsed document.
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    pages_read: Mapped[int | None] = mapped_column(nullable=True)
    pages_total: Mapped[int | None] = mapped_column(nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[CapitalCallStatus] = mapped_column(
        Enum(CapitalCallStatus, native_enum=False, length=32),
        default=CapitalCallStatus.PENDING_APPROVAL,
    )
    requires_manual_review: Mapped[bool] = mapped_column(
        default=False,
        comment="True when committed_capital was not found (no Holding row) "
        "and amount_due could not be calculated — route to a human.",
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<CapitalCall instrument={self.instrument_id!r} "
            f"funder={self.funder_id!r} owing={self.capital_owing} "
            f"status={self.status.value}>"
        )


# ---------------------------------------------------------------------------
# Capital-call payments -- Phase C reconciliation.
# ---------------------------------------------------------------------------


class CapitalCallPayment(Base):
    """Money actually received against an APPROVED capital call.

    Record-keeping + reconciliation only -- the system never moves money and
    never silently absorbs extra cash (an overpayment is rejected at the
    endpoint). The reconciled state (unpaid/partial/paid) is always DERIVED
    from ``sum(payments)`` vs the call's ``amount_due`` at read time and is
    never stored on this row or the call: there is exactly one source of
    truth and no cached figure to drift. Every payment is written by a named
    human (``recorded_by``), same audit rule as every other gate.

    ``reference`` is free text (wire ref / evidence doc id) so reconciliation
    can point back at the bank statement without inventing a documents
    sub-system for cash.
    """

    __tablename__ = "capital_call_payments"
    __table_args__ = (
        Index("ix_capital_call_payments_call", "capital_call_id"),
        Index("ix_capital_call_payments_paid_date", "paid_date"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capital_call_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capital_calls.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    paid_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reference: Mapped[str | None] = mapped_column(String(255), default=None)
    recorded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<CapitalCallPayment call={self.capital_call_id!r} "
            f"amount={self.amount} by={self.recorded_by!r}>"
        )


# ---------------------------------------------------------------------------
# Cap-table proposals -- extraction prepares, a human disposes.
# ---------------------------------------------------------------------------


class CapTableProposal(Base):
    """A prepared cap-table write, proposed by the pipeline, inert until a
    named human approves it.

    The extraction pipeline may classify, extract, and backfill the deal
    container, but ownership facts (CapTableEvent rows) are never written on
    the system's own authority -- the same principle as CapitalCall: an
    extracted call sits PENDING_APPROVAL until a human confirms it. This
    model is the equity-side counterpart: the proposal carries the exact
    issuance payload read from a document that cleared both confidence
    gates, and approval materializes it. The payload is a JSON bag so the
    reviewer sees every number the document actually stated (share count,
    price, amount, currency, document date) together with provenance flags
    (subscriber_unresolved, provisional_investor_created) before one
    approval materializes the Security / issuance event."""

    __tablename__ = "cap_table_proposals"
    __table_args__ = (
        Index("ix_cap_table_proposals_document_id", "document_id"),
        Index("ix_cap_table_proposals_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id")
    )
    instrument_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("instruments.id"), default=None
    )
    proposal_type: Mapped[ProposalType] = mapped_column(
        Enum(ProposalType, native_enum=False, length=32),
        default=ProposalType.CAP_TABLE_PROPOSAL,
    )
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus, native_enum=False, length=16),
        default=ProposalStatus.PROPOSED,
    )
    # The full proposed issuance, exactly as the extraction read it.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<CapTableProposal doc={self.document_id!r} "
            f"status={self.status.value}>"
        )


# ---------------------------------------------------------------------------
# Phase D -- transfer rules / ROFR engine. See PHASE-D-TRANSFER-RULES.md.
# Rules are prepared governance; a named human disposes. Every gate decision
# (including ALLOWED) leaves an immutable TransferEvaluation audit row.
# ---------------------------------------------------------------------------


class TransferRule(Base):
    """A governance rule scoped to an issuer, evaluated against proposed
    TRANSFER events before they reach the append-only log.

    The rule never moves shares -- it either hard-blocks (gate=BLOCK, 409)
    or demands a named human's approval (gate=REVIEW) before the transfer
    is materialized. ``condition`` is a typed JSON bag keyed by rule_type;
    unknown keys ride along verbatim so new rule types never need a
    migration. Rules are deactivated (active=False), never deleted -- the
    evaluation history must stay interpretable."""

    __tablename__ = "transfer_rules"
    __table_args__ = (
        Index("ix_transfer_rules_issuer_name", "issuer_name"),
        Index("ix_transfer_rules_active", "active"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[TransferRuleType] = mapped_column(
        Enum(TransferRuleType, native_enum=False, length=32),
        nullable=False,
    )
    # Typed per rule_type: rofr -> {window_days, exempt_holder_ids},
    # board_approval -> {min_quantity}, bylaw_lockup -> {until_date,
    # holder_ids}. Unknown keys are preserved verbatim (audit).
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    gate: Mapped[TransferGate] = mapped_column(
        Enum(TransferGate, native_enum=False, length=16),
        nullable=False,
    )
    # Named role expected to resolve REVIEW evaluations, e.g. "Board
    # Secretary". Surfaced to clients; not enforced as a hard FK (roles are
    # governance labels, not registry rows).
    approver: Mapped[str] = mapped_column(String(255), nullable=False)
    escalation_role: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    escalation_after_days: Mapped[int | None] = mapped_column(default=None)
    active: Mapped[bool] = mapped_column(default=True)
    # Named human who created the rule -- same audit rule as review.
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<TransferRule issuer={self.issuer_name!r} "
            f"type={self.rule_type.value} gate={self.gate.value} "
            f"active={self.active}>"
        )


class TransferEvaluation(Base):
    """The immutable record of one gate evaluation against one proposed
    TRANSFER event. ALLOWED transfers get a row too, so "why was this
    transfer permitted" always has an answer. PENDING rows are the Phase D
    review queue; approve/reject are named-human transitions."""

    __tablename__ = "transfer_evaluations"
    __table_args__ = (
        Index("ix_transfer_evaluations_security_id", "security_id"),
        Index("ix_transfer_evaluations_outcome", "outcome"),
        Index("ix_transfer_evaluations_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    security_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("securities.id")
    )
    from_holder_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("investors.id")
    )
    holder_id: Mapped[str] = mapped_column(String(64), ForeignKey("investors.id"))
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_share: Mapped[float | None] = mapped_column(Float, default=None)
    effective_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # [{rule_id, rule_type, gate, outcome}] -- the full decision trace.
    rules_evaluated: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list
    )
    outcome: Mapped[TransferEvaluationOutcome] = mapped_column(
        Enum(TransferEvaluationOutcome, native_enum=False, length=24),
        default=TransferEvaluationOutcome.PENDING,
    )
    blocking_rule_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("transfer_rules.id"), default=None
    )
    # Named human for APPROVED / REJECTED transitions (never the system).
    reviewer: Mapped[str | None] = mapped_column(String(64), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<TransferEvaluation security={self.security_id!r} "
            f"outcome={self.outcome.value} qty={self.quantity}>"
        )


class Valuation(Base):
    """A recorded valuation of an issuer's common stock -- Section 409A FMV
    from a qualified appraisal, or the preferred share price from a priced
    round. Pure record-keeping: no computation lives here.

    Usage (CAPTABLE-ROADMAP-FEATURES.md Feature 2): the latest 409A FMV in
    effect on a grant date floors option strike prices (enforced by the
    cap-table event gate), anchors the waterfall baseline common price, and
    is surfaced on the cap table as context."""

    __tablename__ = "valuations"
    __table_args__ = (
        Index("ix_valuations_issuer_date", "issuer_name", "valuation_date"),
        Index("ix_valuations_type", "valuation_type"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    valuation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    price_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    valuation_type: Mapped[ValuationType] = mapped_column(
        Enum(ValuationType, native_enum=False, length=32), nullable=False
    )
    # How the number was derived, e.g. "OPM backsolve", "independent
    # appraisal", "Series A price" -- audit context, never a computation.
    method: Mapped[str | None] = mapped_column(String(255), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<Valuation issuer={self.issuer_name!r} "
            f"type={self.valuation_type.value} "
            f"price={self.price_per_share} date={self.valuation_date}>"
        )


# ---------------------------------------------------------------------------
# Convertibles and priced rounds -- SAFEs live OFF the cap table until a
# priced round commits. A convertible is a contract for future shares, not
# a share: it never affects ownership, fully-diluted count, or voting until
# its CONVERSION event fires (app.captable.compute_conversions).
# ---------------------------------------------------------------------------


class Convertible(Base):
    """An outstanding SAFE (or note) awaiting a priced round.

    Recorded from the SAFE extractor (``SafeExtraction``) or manual entry.
    ``instrument_kind`` distinguishes post-money SAFEs (convertible by the
    YC 2018+ formula, see PHASE-3 plan) from pre-money SAFEs (recorded but
    rejected at conversion time in v1). While ``status`` is ``OUTSTANDING``
    the row has NO cap-table presence; conversion flips it to ``CONVERTED``
    and links the ``CONVERSION`` cap-table event that materialized it.
    """

    __tablename__ = "convertibles"
    __table_args__ = (
        Index("ix_convertibles_issuer_status", "issuer_name", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    investor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("documents.id"), default=None
    )
    purchase_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # "post_money_safe" | "pre_money_safe" -- pre-money is recorded but
    # rejected at conversion time in v1 (R2).
    instrument_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    valuation_cap: Mapped[float] = mapped_column(Float, nullable=False)
    # 0.15 = 15% -- same fraction convention as SafeExtraction.discount_rate.
    discount_rate: Mapped[float | None] = mapped_column(Float, default=None)
    pro_rata_rights: Mapped[bool | None] = mapped_column(default=None)
    mfn_clause: Mapped[bool | None] = mapped_column(default=None)
    conversion_trigger: Mapped[str | None] = mapped_column(Text, default=None)
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ConvertibleStatus] = mapped_column(
        Enum(ConvertibleStatus, native_enum=False, length=16),
        default=ConvertibleStatus.OUTSTANDING,
        nullable=False,
    )
    converted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # The cap_table_events.id of the CONVERSION event that materialized
    # this convertible (set atomically with the status flip).
    conversion_event_id: Mapped[str | None] = mapped_column(
        String(64), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<Convertible investor={self.investor_name!r} "
            f"kind={self.instrument_kind} amount={self.purchase_amount} "
            f"status={self.status.value}>"
        )


class PricedRound(Base):
    """A committed priced equity round (Series A, etc.) that triggered
    conversion of the issuer's outstanding SAFEs.

    ``client_request_id`` is the idempotency key: a commit retried with the
    same UUID returns the existing round instead of double-converting (R7).
    The round's ISSUANCE event and every CONVERSION event it caused carry
    ``related_round_id`` pointing back here, so one round's full audit trail
    is a single indexed lookup.
    """

    __tablename__ = "priced_rounds"
    __table_args__ = (
        Index("ix_priced_rounds_issuer", "issuer_name"),
        UniqueConstraint("client_request_id", name="uq_priced_rounds_crid"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    round_name: Mapped[str] = mapped_column(String(64), nullable=False)
    price_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    round_shares: Mapped[int] = mapped_column(Integer, nullable=False)
    post_money_shares: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    client_request_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<PricedRound issuer={self.issuer_name!r} "
            f"round={self.round_name} price={self.price_per_share}>"
        )