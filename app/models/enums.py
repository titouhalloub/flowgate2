"""Domain enums for the Flowgate unified private-capital pipeline.

These enum definitions are the single source of truth used by both the
SQLAlchemy ORM layer and the Pydantic validation layer.
"""

from enum import Enum


class ComplianceMode(str, Enum):
    TRADITIONAL = "traditional"
    ISLAMIC = "islamic"


class TransactionType(str, Enum):
    LOAN = "loan"
    EQUITY = "equity"
    SUKUK = "sukuk"
    PRIVATE_EQUITY = "private_equity"
    VENTURE_CAPITAL = "venture_capital"
    REAL_ASSET = "real_asset"
    FUND_INTEREST = "fund_interest"


class ShariahContractType(str, Enum):
    MURABAHA = "murabaha"
    IJARA = "ijara"
    MUSHARAKAH = "musharakah"
    WAKALAH = "wakalah"
    NONE = "none"


class DocumentType(str, Enum):
    TERM_SHEET = "term_sheet"
    LOAN_AGREEMENT = "loan_agreement"
    SHA = "shareholder_agreement"
    PPM = "private_placement_memorandum"
    LPA = "limited_partnership_agreement"
    SUKUK_CERTIFICATE = "sukuk_certificate"
    FATWA = "fatwa"
    FINANCIAL_STATEMENT = "financial_statement"
    KYC = "kyc"
    SIDE_LETTER = "side_letter"
    SAFE = "safe"
    SUBSCRIPTION_AGREEMENT = "subscription_agreement"
    EQUITY_SUBSCRIPTION = "equity_subscription"
    CAPITAL_CALL_NOTICE = "capital_call_notice"
    UNCLASSIFIED = "unclassified"
    OTHER = "other"


class ShariahReviewStatus(str, Enum):
    """Replaces the bare bool. The system may only ever set
    SYSTEM_FLAGGED_NONCOMPLIANT or PENDING_SCHOLAR_REVIEW.

    SCHOLAR_APPROVED and SCHOLAR_REJECTED are *human-only* transitions and
    are enforced by the model validator / human-review context in
    ``app.models.review``.
    """

    NOT_APPLICABLE = "not_applicable"
    SYSTEM_FLAGGED_NONCOMPLIANT = "system_flagged_noncompliant"
    PENDING_SCHOLAR_REVIEW = "pending_scholar_review"
    SCHOLAR_APPROVED = "scholar_approved"
    SCHOLAR_REJECTED = "scholar_rejected"


# ---------------------------------------------------------------------------
# These are module-level helper constants, NOT enum members. They are defined
# *outside* the Enum body on purpose: Python's Enum machinery turns any
# non-method assignment inside the class body into another enum member, which
# would silently make these "helper sets" phantom members with meaningless
# frozenset-string values. That was a real safety bug in the ORM validator.
# ---------------------------------------------------------------------------

# The system may set these on its own authority (ORM @validates guard allows):
SYSTEM_SETTABLE = frozenset(
    {
        ShariahReviewStatus.NOT_APPLICABLE,
        ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT,
        ShariahReviewStatus.PENDING_SCHOLAR_REVIEW,
    }
)
# Only a human reviewer may set these (ORM @validates guard blocks these):
HUMAN_ONLY = frozenset(
    {ShariahReviewStatus.SCHOLAR_APPROVED, ShariahReviewStatus.SCHOLAR_REJECTED}
)


class IngestionSource(str, Enum):
    NATIVE_EXTRACTION = "native_extraction"
    VENDOR_IMPORT = "vendor_import"  # e.g. Canoe / Passthrough API
    MANUAL_ENTRY = "manual_entry"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    REVIEW_NEEDED = "review_needed"  # low confidence / unclassified
    FAILED = "failed"


class LedgerEntryType(str, Enum):
    CATEGORY_MUTATION = "category_mutation"  # a line item, e.g. capital call
    DOCUMENT_RESULT = "document_result"
    COMPLIANCE_EVENT = "compliance_event"
    CAP_TABLE_EVENT = "cap_table_event"
    CAP_TABLE_PROPOSAL = "cap_table_proposal"
    CAPITAL_CALL_REVIEW = "capital_call_review"  # named-reviewer approve/reject gate
    CAPITAL_CALL_PAYMENT = "capital_call_payment"  # recorded receipt against an approved call
    TRANSFER_EVALUATION = "transfer_evaluation"  # Phase D gate decision on a proposed transfer


class ProposalStatus(str, Enum):
    """Lifecycle of a proposed cap-table event. The system never writes
    ownership-changing facts on its own: extraction produces a PROPOSED
    event, and only a named human reviewer can move it to APPROVED (which
    materializes a real CapTableEvent) or REJECTED."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProposalType(str, Enum):
    """Kind of prepared write a ``CapTableProposal`` carries (see
    ``app.models.orm.CapTableProposal``). v1 ships the equity-issuance
    proposal; future kinds (transfer, conversion, cancellation) extend this
    vocabulary without changing the human approval gate."""

    CAP_TABLE_PROPOSAL = "cap_table_proposal"


class SecurityType(str, Enum):
    """Classes of equity a company can issue. Kept as vocabulary here; the DB
    column is a validated string (see app.models.orm.Security) so the Alembic
    chain stays plain-varchar and portable across SQLite/Postgres."""

    COMMON = "common"
    PREFERRED = "preferred"
    OPTION = "option"
    WARRANT = "warrant"
    SAFE = "safe"
    CONVERTIBLE_NOTE = "convertible_note"


class CapTableEventType(str, Enum):
    """Append-only cap-table event vocabulary. Positions are *never* stored --
    they are recomputed by replaying these (see app.captable.compute_cap_table).

    EXERCISE: option -> common, same holder. CONVERSION: SAFE/note ->
    preferred or common, same holder."""

    ISSUANCE = "issuance"
    TRANSFER = "transfer"
    CANCELLATION = "cancellation"
    EXERCISE = "exercise"
    CONVERSION = "conversion"


class InvestorType(str, Enum):
    """FUND is what makes a cross-fund portfolio view a native join here,
    not a portal-scraping integration like every competitor's."""

    INDIVIDUAL = "individual"
    INSTITUTION = "institution"
    FUND = "fund"


class HoldingStatus(str, Enum):
    ACTIVE = "active"
    EXITED = "exited"


class CapitalCallStatus(str, Enum):
    """Lifecycle of a capital call ingestion. The system never moves money
    on its own: an extracted call is PENDING_APPROVAL until a human reviewer
    confirms it through the approval gate."""

    PENDING_COMMITMENT_LOOKUP = "pending_commitment_lookup"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Phase D -- transfer rules / ROFR engine. Rules are prepared governance; a
# named human disposes. See PHASE-D-TRANSFER-RULES.md.
# ---------------------------------------------------------------------------


class TransferRuleType(str, Enum):
    """Vocabulary of governance rules evaluated against proposed TRANSFER
    events. The engine reads only the condition keys documented in
    PHASE-D-TRANSFER-RULES.md; unknown keys ride along verbatim in the
    audit record so new rule types never need a migration."""

    ROFR = "rofr"
    BOARD_APPROVAL = "board_approval"
    BYLAW_LOCKUP = "bylaw_lockup"


class TransferGate(str, Enum):
    """What an active rule does to a triggering transfer. BLOCK is a hard
    409 (no human can waive it through this API); REVIEW requires a named
    approver to materialize the transfer."""

    BLOCK = "block"
    REVIEW = "review"


class TransferEvaluationOutcome(str, Enum):
    """Lifecycle of one gate decision on one proposed transfer. Every
    outcome -- including ALLOWED -- is an immutable audit row."""

    PENDING = "pending"
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    APPROVED = "approved"
    REJECTED = "rejected"
