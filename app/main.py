"""Flowgate API -- exposes the tested pipeline (classification, extraction,
configurable compliance, ledger) as a running service.

This is deliberately thin: every route is a wrapper around functions in
app.pipeline / app.review / app.compliance that already have their own test
coverage. The API layer's job is auth, request/response shaping, and error
handling -- not business logic.
"""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_schemas import (
    CapitalCallCreate,
    CapitalCallOut,
    CapitalCallReviewRequest,
    PaymentCreate,
    PaymentOut,
    CapTableEventCreate,
    CapTableEventOut,
    CapTableOut,
    CapTableProposalOut,
    DocumentOut,
    DocumentSubmit,
    ErrorOut,
    EvidenceDocumentSubmit,
    GrantVestingOut,
    HoldingCreate,
    HoldingOut,
    HolderPositionOut,
    HumanReviewRequest,
    InstrumentCreate,
    InstrumentOut,
    InvestorCreate,
    InvestorOut,
    InvestorPortfolioOut,
    LedgerEntryOut,
    PipelineRunOut,
    PipelineUploadOut,
    PortfolioHoldingOut,
    SecurityCreate,
    SecurityOut,
    TransferEvaluationOut,
    TransferRuleCreate,
    TransferRuleOut,
    ValuationCreate,
    ValuationOut,
    LatestValuationOut,
)
from app.captable import CapTableError, compute_cap_table
from app.compliance import ComplianceGateway
from app.config import settings
from app.db import get_session, init_db
from app.models.enums import (
    CapTableEventType,
    CapitalCallStatus,
    ComplianceMode,
    DocumentStatus,
    IngestionSource,
    InvestorType,
    LedgerEntryType,
    ProposalStatus,
    ProposalType,
    SecurityType,
    ShariahReviewStatus,
    TransferEvaluationOutcome,
    TransferGate,
    TransferRuleType,
    ValuationType,
)
from app.models.orm import (
    CapTableEvent,
    CapTableProposal,
    CapitalCall,
    CapitalCallPayment,
    Document,
    Holding,
    Instrument,
    Investor,
    LedgerEntry,
    Security as SecurityModel,
    TransferEvaluation,
    TransferRule,
    Valuation,
)
from app.models.orm import _utcnow
from app.pipeline import process_document
from app.ocr import TextExtractionError, UnsupportedFileType, UploadTooLarge, text_from_upload
from app.review import ShariahReviewError, submit_human_review_instrument
from app.schemas import EquitySubscriptionExtraction
from app.transfer_rules import (
    TransferRuleError,
    evaluate_transfer_rules,
    validate_rule_condition,
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Flowgate API",
    description="Unified private-capital pipeline: classification, extraction, "
    "configurable compliance (traditional + Islamic), ledger.",
    version="0.1.0",
    lifespan=_lifespan,
)

# Wide open for the MVP demo UI to call from a static page during pilot
# conversations. Tighten to real origins before any actual customer data
# flows through this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_dist_dir = Path(__file__).resolve().parent.parent / "dist"
_static_dir = _dist_dir if (_dist_dir / "index.html").is_file() else Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
def root() -> FileResponse:
    """Serve the React app at the root URL, falling back to the legacy demo."""
    index = _static_dir / "index.html"
    return FileResponse(str(index))





# --------------------------------------------------------------------------- #
# Auth -- a real, if minimal, gate. Not full OAuth, but not a fully open
# unauthenticated endpoint either, now that this is meant for real prospects.
# --------------------------------------------------------------------------- #

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(_api_key_header)) -> str:
    if not settings.api_keys:
        # No keys configured: fail closed, not open. An empty allowlist
        # should never silently mean "anyone can call this."
        raise HTTPException(
            status_code=503,
            detail="No API keys configured on the server (A27_API_KEYS unset).",
        )
    valid_keys = {k.strip() for k in settings.api_keys.split(",") if k.strip()}
    if not key or not any(secrets.compare_digest(key, k) for k in valid_keys):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key.")
    return key


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Instruments
# --------------------------------------------------------------------------- #


@app.post(
    "/instruments",
    response_model=InstrumentOut,
    status_code=201,
    responses={401: {"model": ErrorOut}},
)
def create_instrument(
    payload: InstrumentCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> Instrument:
    instrument = Instrument(
        id=str(uuid4()),
        transaction_type=payload.transaction_type,
        compliance_mode=payload.compliance_mode,
        issuer_name=payload.issuer_name,
        issuer_type=payload.issuer_type,
        amount=payload.amount,
        currency=payload.currency,
        maturity_date=payload.maturity_date,
        type_specific_data={},
    )
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    return instrument


@app.get(
    "/instruments/{instrument_id}",
    response_model=InstrumentOut,
    responses={404: {"model": ErrorOut}},
)
def get_instrument(
    instrument_id: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> Instrument:
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id!r} not found")
    return instrument


@app.get(
    "/instruments/{instrument_id}/ledger",
    response_model=list[LedgerEntryOut],
    responses={404: {"model": ErrorOut}},
)
def get_instrument_ledger(
    instrument_id: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[LedgerEntry]:
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id!r} not found")
    rows = session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.instrument_id == instrument_id)
        .order_by(LedgerEntry.created_at)
    ).scalars().all()
    return list(rows)
# --------------------------------------------------------------------------- #
# Documents -- the actual pipeline entry point
# --------------------------------------------------------------------------- #


@app.post(
    "/instruments/{instrument_id}/documents",
    response_model=PipelineRunOut,
    responses={404: {"model": ErrorOut}},
)
def submit_document(
    instrument_id: str,
    payload: DocumentSubmit,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> PipelineRunOut:
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id!r} not found")

    result = process_document(
        session, instrument, ComplianceGateway(), payload.text, filename=payload.filename
    )
    session.refresh(instrument)

    return PipelineRunOut(
        document=DocumentOut.model_validate(result.document),
        instrument=InstrumentOut.model_validate(instrument),
        outcome=result.outcome,
        routed_to_review=result.routed,
    )


@app.post(
    "/instruments/{instrument_id}/documents/upload",
    response_model=PipelineUploadOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        400: {"model": ErrorOut},
        413: {"model": ErrorOut},
        422: {"model": ErrorOut},
    },
)
def upload_document(
    instrument_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> PipelineUploadOut:
    """Real-document intake: PDF / TXT / MD / HTML / image upload. The
    file's embedded text layer is read first; scans fall back to Tesseract
    OCR (the accepted MVP trade-off, stated in app.ocr). Everything
    downstream -- classification, extraction, compliance, ledger -- is the
    same pipeline the text endpoint feeds. Unparseable documents fail loudly
    (422) with the reason; the pipeline never guesses."""
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id!r} not found")

    page_meta: dict = {}
    try:
        text = text_from_upload(file, meta=page_meta)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except TextExtractionError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{exc} The document could not be parsed, so nothing was "
            "classified or extracted -- no guessing.",
        ) from exc

    # Persist the original so file_url in the DB points at a real file the
    # reviewer (or a developer tuning the extractors) can open later.
    stored_url: str | None = None
    try:
        upload_dir = Path(settings.uploads_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        file.file.seek(0)
        raw = file.file.read()
        file.file.seek(0)
        safe_name = f"{uuid4().hex}_{(file.filename or 'upload').replace('/', '_').replace(chr(92), '_')}"
        (upload_dir / safe_name).write_bytes(raw)
        stored_url = str(upload_dir / safe_name)
    except OSError:
        stored_url = None  # storage failure must not block ingestion

    result = process_document(
        session, instrument, ComplianceGateway(), text, filename=file.filename or "upload",
        file_url=stored_url,
    )
    session.refresh(instrument)

    return PipelineUploadOut(
        document=DocumentOut.model_validate(result.document),
        instrument=InstrumentOut.model_validate(instrument),
        outcome=result.outcome,
        routed_to_review=result.routed,
        extracted_text=text,
        pages_read=page_meta.get("pages_read"),
        pages_total=page_meta.get("pages_total"),
    )


@app.post(
    "/instruments/{instrument_id}/evidence",
    response_model=DocumentOut,
    status_code=201,
    responses={404: {"model": ErrorOut}},
)
def submit_evidence_document(
    instrument_id: str,
    payload: EvidenceDocumentSubmit,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> Document:
    """Attach a supporting document (fatwa, KYC, side letter) that the
    compliance gateway needs to see as evidence, without running it through
    extraction -- there is no structured schema to extract a fatwa into, and
    forcing one through the same pipeline as loan/sukuk documents would
    either misclassify it or route it to review for the wrong reason.
    """
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id!r} not found")

    document = Document(
        id=str(uuid4()),
        instrument_id=instrument.id,
        filename=payload.filename,
        file_url="mem://" + uuid4().hex,
        document_type=payload.document_type,
        classification_confidence=1.0,  # explicitly typed by the caller, not classified
        ingestion_source=IngestionSource.MANUAL_ENTRY,
        compliance_mode=instrument.compliance_mode,
        status=DocumentStatus.PROCESSED,
        extracted_data={"raw_text": payload.text},
    )
    session.add(document)
    session.add(
        LedgerEntry(
            id=str(uuid4()),
            entry_type=LedgerEntryType.DOCUMENT_RESULT,
            instrument_id=instrument.id,
            document_id=document.id,
            payload={"stage": "evidence_attached", "document_type": payload.document_type.value},
        )
    )
    session.commit()
    session.refresh(document)
    return document


# --------------------------------------------------------------------------- #
# Human review -- the only path to SCHOLAR_APPROVED / SCHOLAR_REJECTED
# --------------------------------------------------------------------------- #


@app.post(
    "/instruments/{instrument_id}/review",
    response_model=InstrumentOut,
    responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
def review_instrument(
    instrument_id: str,
    payload: HumanReviewRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> Instrument:
    try:
        return submit_human_review_instrument(
            session,
            instrument_id,
            reviewer_id=payload.reviewer_id,
            decision=payload.decision,  # type: ignore[arg-type]
            notes=payload.notes,
        )
    except ShariahReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
# --------------------------------------------------------------------------- #
# Cap table -- the live cap-table demo panel
# --------------------------------------------------------------------------- #


@app.post(
    "/investors",
    response_model=InvestorOut,
    status_code=201,
    responses={401: {"model": ErrorOut}},
)
def create_investor(
    payload: InvestorCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> Investor:
    investor = Investor(
        id=str(uuid4()),
        name=payload.name,
        investor_type=InvestorType(payload.investor_type),
        kyc_verified=False,
    )
    session.add(investor)
    session.commit()
    session.refresh(investor)
    return investor


@app.get(
    "/investors",
    response_model=list[InvestorOut],
    responses={401: {"model": ErrorOut}},
)
def list_investors(
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[Investor]:
    """Picker list for the proposal review UI: when a proposal's subscriber
    is unresolved, the reviewer links one of *these* known investors to it --
    the holder on a cap-table event must always be a real Investor row."""
    return list(
        session.execute(select(Investor).order_by(Investor.name)).scalars().all()
    )


# --------------------------------------------------------------------------- #
# Cross-fund portfolio -- one investor's holdings across many funds and both
# compliance tracks, unified in a single response.
# --------------------------------------------------------------------------- #


@app.post(
    "/instruments/{instrument_id}/holdings",
    response_model=HoldingOut,
    status_code=201,
    responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
def create_holding(
    instrument_id: str,
    payload: HoldingCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> Holding:
    """Record an investor's stake in an instrument. Both sides must exist --
    no silent dangling references into the portfolio."""
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(
            status_code=404, detail=f"Instrument {instrument_id!r} not found"
        )
    investor = session.get(Investor, payload.investor_id)
    if investor is None:
        raise HTTPException(
            status_code=404, detail=f"Investor {payload.investor_id!r} not found"
        )

    holding = Holding(
        id=str(uuid4()),
        investor_id=investor.id,
        instrument_id=instrument.id,
        stake_amount=payload.stake_amount,
        ownership_percentage=payload.ownership_percentage,
    )
    session.add(holding)
    session.commit()
    session.refresh(holding)
    return holding


@app.get(
    "/investors/{investor_id}/portfolio",
    response_model=InvestorPortfolioOut,
    responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
def get_investor_portfolio(
    investor_id: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> InvestorPortfolioOut:
    """The cross-fund view: every holding an investor has, across funds and
    across both compliance tracks, with per-track exposure totals -- the same
    unification thesis as the compliance gateway, on the investor side."""
    investor = session.get(Investor, investor_id)
    if investor is None:
        raise HTTPException(
            status_code=404, detail=f"Investor {investor_id!r} not found"
        )

    holding_rows = session.execute(
        select(Holding).where(Holding.investor_id == investor_id)
    ).scalars().all()

    holdings_out: list[PortfolioHoldingOut] = []
    traditional_total = 0.0
    islamic_total = 0.0
    seen_instruments: set[str] = set()
    for holding in holding_rows:
        instrument = session.get(Instrument, holding.instrument_id)
        if instrument is None:  # pragma: no cover -- FK-guarded at write time
            continue
        seen_instruments.add(instrument.id)
        if instrument.compliance_mode == ComplianceMode.TRADITIONAL:
            traditional_total += holding.stake_amount
        elif instrument.compliance_mode == ComplianceMode.ISLAMIC:
            islamic_total += holding.stake_amount
        holdings_out.append(
            PortfolioHoldingOut(
                holding=HoldingOut.model_validate(holding),
                instrument=InstrumentOut.model_validate(instrument),
            )
        )

    return InvestorPortfolioOut(
        investor=InvestorOut.model_validate(investor),
        holdings=holdings_out,
        total_traditional_exposure=round(traditional_total, 2),
        total_islamic_exposure=round(islamic_total, 2),
        fund_count=len(seen_instruments),
    )


@app.post(
    "/securities",
    response_model=SecurityOut,
    status_code=201,
    responses={401: {"model": ErrorOut}},
)
def create_security(
    payload: SecurityCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> SecurityModel:
    security = SecurityModel(
        id=str(uuid4()),
        issuer_name=payload.issuer_name,
        name=payload.name,
        security_type=payload.security_type,
        authorized_shares=payload.authorized_shares,
        par_value=payload.par_value,
    )
    session.add(security)
    session.commit()
    session.refresh(security)
    return security


@app.post(
    "/cap-table-events",
    response_model=CapTableEventOut,
    status_code=201,
    responses={
        401: {"model": ErrorOut},
        400: {"model": ErrorOut},
        404: {"model": ErrorOut},
    },
)
def record_cap_table_event(
    payload: CapTableEventCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapTableEvent:
    # The event must reference securities (and, for exercise/conversion,
    # the target security) and holders that actually exist -- no silent
    # dangling references into the event log.
    security = session.get(SecurityModel, payload.security_id)
    if security is None:
        raise HTTPException(
            status_code=404, detail=f"Security {payload.security_id!r} not found"
        )
    if payload.target_security_id is not None:
        target = session.get(SecurityModel, payload.target_security_id)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail=f"Target security {payload.target_security_id!r} not found",
            )
    for holder_id in (payload.holder_id, payload.from_holder_id):
        if holder_id is None:
            continue
        if session.get(Investor, holder_id) is None:
            raise HTTPException(
                status_code=400, detail=f"Investor {holder_id!r} not found"
            )

    if payload.event_type != CapTableEventType.ISSUANCE.value:
        if (
            payload.vesting_start_date is not None
            or payload.vesting_period_months is not None
            or payload.cliff_months is not None
            or payload.acceleration_clause is not None
        ):
            raise HTTPException(
                status_code=400,
                detail="Vesting schedule fields are only permitted on ISSUANCE events",
            )

    if payload.is_repurchase and payload.event_type != CapTableEventType.CANCELLATION.value:
        raise HTTPException(
            status_code=400,
            detail="is_repurchase may only be True on CANCELLATION events",
        )

    # 409A compliance gate: an option (or warrant) struck below the fair
    # market value in effect on the grant date is a Section 409A violation
    # -- the grantee owes immediate tax and penalties -- so the compliance
    # gateway refuses to record it. The FMV that applies is the latest 409A
    # valuation dated on or before the event's effective date; with no 409A
    # on file yet there is nothing to violate and issuance proceeds. Common
    # and preferred issuances are not strikes and are never gated.
    if (
        payload.event_type == CapTableEventType.ISSUANCE.value
        and payload.price_per_share is not None
        and security.security_type in (SecurityType.OPTION, SecurityType.WARRANT)
    ):
        fmv = session.execute(
            select(Valuation)
            .where(
                Valuation.issuer_name == security.issuer_name,
                Valuation.valuation_type == ValuationType.FMV_409A,
                Valuation.valuation_date <= payload.effective_date,
            )
            .order_by(Valuation.valuation_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if fmv is not None and payload.price_per_share < fmv.price_per_share:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Strike price {payload.price_per_share} is below the 409A "
                    f"fair market value of {fmv.price_per_share} in effect "
                    f"since {fmv.valuation_date.date().isoformat()} -- a "
                    "below-FMV grant violates Section 409A"
                ),
            )

    # Phase D governance gate: every proposed TRANSFER is evaluated against
    # the issuer's active rules BEFORE it reaches the append-only log. The
    # engine commits the immutable evaluation row (and its ledger entry for
    # final outcomes) before returning; ALLOWED falls through to the write.
    if payload.event_type == CapTableEventType.TRANSFER.value:
        if payload.from_holder_id is None:
            raise HTTPException(
                status_code=400,
                detail="A transfer requires from_holder_id",
            )
        evaluation = evaluate_transfer_rules(
            session,
            security,
            {
                "security_id": payload.security_id,
                "from_holder_id": payload.from_holder_id,
                "holder_id": payload.holder_id,
                "quantity": payload.quantity,
                "price_per_share": payload.price_per_share,
                "effective_date": payload.effective_date,
            },
        )
        if evaluation.outcome is TransferEvaluationOutcome.BLOCKED:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Transfer blocked by governance rule",
                    "transfer_evaluation_id": evaluation.id,
                    "blocking_rule_id": evaluation.blocking_rule_id,
                },
            )
        if evaluation.outcome is TransferEvaluationOutcome.PENDING:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Transfer requires governance approval",
                    "transfer_evaluation_id": evaluation.id,
                },
            )

    event = CapTableEvent(
        id=str(uuid4()),
        security_id=payload.security_id,
        target_security_id=payload.target_security_id,
        event_type=payload.event_type,
        holder_id=payload.holder_id,
        from_holder_id=payload.from_holder_id,
        quantity=payload.quantity,
        price_per_share=payload.price_per_share,
        effective_date=payload.effective_date,
        notes=payload.notes,
        vesting_start_date=payload.vesting_start_date,
        vesting_period_months=payload.vesting_period_months,
        cliff_months=payload.cliff_months,
        acceleration_clause=payload.acceleration_clause,
        is_repurchase=payload.is_repurchase,
        repurchase_approver=payload.repurchase_approver,
    )
    session.add(event)
    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001 -- surfaced as a real 400, not a 500
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.refresh(event)

    # Validate the whole log is still consistent -- catches an overdraft
    # transfer/cancellation/exercise/vesting constraint at write time
    # (409/400 + the offending event rolled back), not silently at the next read.
    try:
        compute_cap_table(session, security.issuer_name)
    except CapTableError as exc:
        session.delete(event)
        session.commit()
        msg = str(exc)
        status = 409 if any(k in msg.lower() for k in ("vested", "repurchase", "unvested")) else 400
        raise HTTPException(status_code=status, detail=msg) from exc

    if payload.is_repurchase:
        session.add(
            LedgerEntry(
                id=str(uuid4()),
                entry_type=LedgerEntryType.CAP_TABLE_EVENT,
                payload={
                    "event": "vested_repurchase",
                    "event_id": event.id,
                    "security_id": payload.security_id,
                    "from_holder_id": payload.from_holder_id,
                    "quantity": payload.quantity,
                    "repurchase_approver": payload.repurchase_approver,
                },
            )
        )
        session.commit()

    return event


@app.get(
    "/cap-table/{issuer_name}",
    response_model=CapTableOut,
    responses={401: {"model": ErrorOut}, 400: {"model": ErrorOut}},
)
def get_cap_table(
    issuer_name: str,
    as_of: datetime | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapTableOut:
    try:
        snapshot = compute_cap_table(session, issuer_name, as_of=as_of)
    except CapTableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    holder_ids = {p.holder_id for p in snapshot.positions}
    security_ids = {p.security_id for p in snapshot.positions}
    holders = {
        h.id: h.name
        for h in session.execute(
            select(Investor).where(Investor.id.in_(holder_ids))
        ).scalars()
    } if holder_ids else {}
    securities = {
        s.id: s.name
        for s in session.execute(
            select(SecurityModel).where(SecurityModel.id.in_(security_ids))
        ).scalars()
    } if security_ids else {}

    ownership = snapshot.ownership_by_holder()
    total = snapshot.total_fully_diluted_shares
    positions_out = [
        HolderPositionOut(
            holder_id=p.holder_id,
            holder_name=holders.get(p.holder_id, "unknown"),
            security_id=p.security_id,
            security_name=securities.get(p.security_id, "unknown"),
            shares=p.shares,
            vested_shares=p.vested_shares,
            unvested_shares=p.unvested_shares,
            # Per-position share of the fully-diluted total. The holder's
            # overall percentage is ownership_by_holder -- repeating it on
            # every row invited clients to double-count a holder with
            # shares in more than one security class (a real bug the demo
            # JS hit).
            ownership_percent=(
                round(p.shares / total * 100, 4) if total > 0 else 0.0
            ),
        )
        for p in snapshot.positions
    ]

    grants_out = [
        GrantVestingOut(
            event_id=g.event_id,
            security_id=g.security_id,
            holder_id=g.holder_id,
            original_shares=g.original_shares,
            total_shares=g.total_shares,
            vested_shares=g.vested_shares,
            unvested_shares=g.unvested_shares,
            transferred_vested_shares=g.transferred_vested_shares,
            repurchased_vested_shares=g.repurchased_vested_shares,
            vesting_start_date=g.vesting_start_date,
            vesting_period_months=g.vesting_period_months,
            cliff_months=g.cliff_months,
            cliff_date=g.cliff_date,
            fully_vested_date=g.fully_vested_date,
            is_fully_vested=g.is_fully_vested,
            acceleration_clause=g.acceleration_clause,
        )
        for g in snapshot.grants
    ]

    # 409A context: the FMV in effect as of the snapshot date (latest
    # 409A valuation dated on or before it), plus the staleness nag --
    # a 409A older than 12 months needs refreshing, but it still floors
    # strike prices until a new valuation lands.
    fmv = session.execute(
        select(Valuation)
        .where(
            Valuation.issuer_name == issuer_name,
            Valuation.valuation_type == ValuationType.FMV_409A,
            Valuation.valuation_date <= snapshot.as_of,
        )
        .order_by(Valuation.valuation_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    return CapTableOut(
        issuer_name=snapshot.issuer_name,
        as_of=snapshot.as_of,
        total_fully_diluted_shares=total,
        total_vested_shares=snapshot.total_vested_shares,
        total_unvested_shares=snapshot.total_unvested_shares,
        shares_by_security=snapshot.shares_by_security,
        ownership_by_holder=ownership,
        positions=positions_out,
        grants=grants_out,
        latest_409a_price=fmv.price_per_share if fmv is not None else None,
        latest_409a_date=fmv.valuation_date if fmv is not None else None,
        latest_409a_stale=(
            fmv is not None
            and _months_old(fmv.valuation_date, snapshot.as_of) > _STALE_AFTER_MONTHS
        ),
    )


# ---------------------------------------------------------------------------
# 409A valuations -- record-keeping for issuer fair market value
# (CAPTABLE-ROADMAP-FEATURES.md Feature 2)
# ---------------------------------------------------------------------------

# A 409A older than 12 months is stale: surfaced as a warning (nag) on the
# latest-valuation read and the cap table -- never a hard block.
_STALE_AFTER_MONTHS = 12.0


def _months_old(valuation_date: datetime, ref: datetime) -> float:
    """Age of a valuation in (average) months, naive/aware safe."""
    a = valuation_date if valuation_date.tzinfo else valuation_date.replace(tzinfo=timezone.utc)
    b = ref if ref.tzinfo else ref.replace(tzinfo=timezone.utc)
    return max(0.0, (b - a).days / 30.4375)


@app.post(
    "/valuations",
    response_model=ValuationOut,
    status_code=201,
    responses={401: {"model": ErrorOut}},
)
def record_valuation(
    payload: ValuationCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> Valuation:
    valuation = Valuation(
        id=str(uuid4()),
        issuer_name=payload.issuer_name,
        valuation_date=payload.valuation_date,
        price_per_share=payload.price_per_share,
        valuation_type=ValuationType(payload.valuation_type),
        method=payload.method,
        notes=payload.notes,
    )
    session.add(valuation)
    session.commit()
    session.refresh(valuation)
    return valuation


@app.get(
    "/valuations/{issuer_name}",
    response_model=list[ValuationOut],
    responses={401: {"model": ErrorOut}},
)
def list_valuations(
    issuer_name: str,
    valuation_type: str | None = Query(
        default=None, pattern="^(fmv_409a|preferred_price_round)$"
    ),
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[Valuation]:
    stmt = (
        select(Valuation)
        .where(Valuation.issuer_name == issuer_name)
        .order_by(Valuation.valuation_date.desc(), Valuation.created_at.desc())
    )
    if valuation_type is not None:
        stmt = stmt.where(Valuation.valuation_type == ValuationType(valuation_type))
    return list(session.execute(stmt).scalars().all())


@app.get(
    "/valuations/{issuer_name}/latest",
    response_model=LatestValuationOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        400: {"model": ErrorOut},
    },
)
def latest_valuation(
    issuer_name: str,
    valuation_type: str = Query(
        default="fmv_409a", pattern="^(fmv_409a|preferred_price_round)$"
    ),
    as_of: datetime | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> LatestValuationOut:
    """The current valuation of a given type, as of now (or an explicit
    date). Staleness is a nag, not a block: a 409A older than 12 months
    still floors strike prices until a new valuation is recorded."""
    ref = as_of or datetime.now(timezone.utc)
    row = session.execute(
        select(Valuation)
        .where(
            Valuation.issuer_name == issuer_name,
            Valuation.valuation_type == ValuationType(valuation_type),
            Valuation.valuation_date <= ref,
        )
        .order_by(Valuation.valuation_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No {valuation_type} valuation on file for {issuer_name!r}",
        )
    months_old = _months_old(row.valuation_date, ref)
    return LatestValuationOut(
        id=row.id,
        issuer_name=row.issuer_name,
        valuation_date=row.valuation_date,
        price_per_share=row.price_per_share,
        valuation_type=row.valuation_type,
        method=row.method,
        notes=row.notes,
        created_at=row.created_at,
        is_stale=months_old > _STALE_AFTER_MONTHS,
        months_old=round(months_old, 1),
    )


# ---------------------------------------------------------------------------
# Document -> cap table proposal flow
#
# The pipeline classifies, extracts, and writes the deal container, but the
# cap table is a *ledger of ownership facts*, and per the no-guessing
# guarantee the system never writes those on its own authority. What it CAN
# do on its own is prepare the exact write for a human: a proposed issuance
# with every number filled from an extraction that already cleared the
# confidence gates, never invented. Approval is one endpoint, one click --
# and the reviewer sees the real numbers, not a blank form to re-type.
#
# Investor auto-provisioning follows the same rule: when the *document itself*
# names the subscriber in its own preamble convention ("X (the 'Subscriber')
# hereby subscribes..."), creating a PROVISIONAL investor with that exact
# name is transcription, not a guess. Signature-block-only names are never
# auto-provisioned -- they stay None and the proposal carries a
# subscriber_unresolved flag for the reviewer.
# ---------------------------------------------------------------------------


def _provisional_investor(
    session: Session, name: str
) -> tuple[Investor, bool]:
    """Return the investor with exactly this name, creating a PROVISIONAL
    one when absent. The bool is True only for a freshly created row, so the
    audit trail distinguishes transcription from reuse."""
    existing = session.execute(
        select(Investor).where(Investor.name == name)
    ).scalars().first()
    if existing is not None:
        return existing, False
    investor = Investor(
        id=str(uuid4()),
        name=name,
        investor_type=InvestorType.INDIVIDUAL,
    )
    session.add(investor)
    session.flush()  # id available for the event payload below
    return investor, True


def _provisional_security(
    session: Session, issuer_name: str, security_type: str | None,
    share_count: float | None,
) -> tuple[SecurityModel, bool]:
    """Return the issuer's security class, creating a placeholder when absent.

    A class with the same name may already exist; otherwise the extraction's
    security_type text ('Series A Preferred stock') becomes the class name.
    authorized_shares is set from the document's stated share count ONLY --
    never padded with a guessed round number."""
    name = (security_type or "common").strip() or "common"
    existing = session.execute(
        select(SecurityModel).where(
            SecurityModel.issuer_name == issuer_name,
            SecurityModel.name == name,
        )
    ).scalars().first()
    if existing is not None:
        return existing, False
    security = SecurityModel(
        id=str(uuid4()),
        issuer_name=issuer_name,
        name=name,
        security_type=SecurityType.PREFERRED
        if "preferred" in name.lower() else SecurityType.COMMON,
        authorized_shares=share_count,
    )
    session.add(security)
    session.flush()
    return security, True


@app.post(
    "/documents/{document_id}/cap-table-proposal",
    response_model=CapTableProposalOut,
    status_code=201,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def create_cap_table_proposal(
    document_id: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapTableProposal:
    """Prepare a cap-table issuance proposal from a processed document.

    The document must have passed both confidence gates (classification >=
    0.75, extraction >= 0.85) -- a reviewed/unprocessed document carries
    numbers nobody validated, so it can never seed a proposal. The proposal
    itself is inert: no Security, Investor, or CapTableEvent rows exist until
    a human approves (see the approval endpoint below)."""
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(
            status_code=404, detail=f"Document {document_id!r} not found"
        )
    if doc.status != DocumentStatus.PROCESSED:
        raise HTTPException(
            status_code=409,
            detail=f"Document {document_id!r} is {doc.status.value}, not "
            "processed -- only a document that cleared both confidence "
            "gates can seed a cap-table proposal",
        )

    data = (doc.extracted_data or {}).get("data", {})
    parsed = EquitySubscriptionExtraction.model_validate(data)
    if not parsed.company_name or parsed.share_count is None:
        raise HTTPException(
            status_code=409,
            detail="Extraction lacks the fields a cap-table event requires "
            "(company_name / share_count) -- route to human review instead",
        )

    investor_id: str | None = None
    provisional_investor_created = False
    if parsed.subscriber_name:
        investor, provisional_investor_created = _provisional_investor(
            session, parsed.subscriber_name
        )
        investor_id = investor.id

    payload = {
        "document_id": doc.id,
        "instrument_id": doc.instrument_id,
        "issuer_name": parsed.company_name,
        "security_name": parsed.security_type,
        "holder_id": investor_id,
        "holder_name": parsed.subscriber_name,
        "share_count": parsed.share_count,
        "price_per_share": parsed.subscription_price_per_share
        or parsed.price_per_unit,
        "amount": parsed.investment_amount or parsed.total_offering_amount,
        "currency": parsed.currency,
        "document_date": (
            parsed.document_date.isoformat() if parsed.document_date else None
        ),
        "subscriber_unresolved": investor_id is None,
        "provisional_investor_created": provisional_investor_created,
    }
    proposal = CapTableProposal(
        id=str(uuid4()),
        document_id=doc.id,
        instrument_id=doc.instrument_id,
        proposal_type=ProposalType.CAP_TABLE_PROPOSAL,
        status=ProposalStatus.PROPOSED,
        payload=payload,
    )
    session.add(proposal)
    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001 -- surfaced as a real 409, not a 500
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.refresh(proposal)
    return proposal


@app.post(
    "/cap-table-proposals/{proposal_id}/approve",
    response_model=CapTableEventOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def approve_cap_table_proposal(
    proposal_id: str,
    reviewer: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapTableEvent:
    """The human gate. Materializes the proposed issuance as a real
    CapTableEvent -- the ONLY path from an extracted document into the
    cap table, matching how CapitalCall approval already works."""
    proposal = session.get(CapTableProposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal {proposal_id!r} not found"
        )
    if proposal.status != ProposalStatus.PROPOSED:
        raise HTTPException(
            status_code=409,
            detail=f"Proposal {proposal_id!r} is {proposal.status.value}, "
            "not proposed -- a proposal is approved at most once",
        )
    if not reviewer or not reviewer.strip():
        raise HTTPException(status_code=409, detail="A named reviewer is required")
    payload = proposal.payload or {}
    if payload.get("subscriber_unresolved"):
        raise HTTPException(
            status_code=409,
            detail="The extraction never identified the subscriber -- "
            "link a real investor (or edit the proposal) before approving",
        )

    issuer_name = payload.get("issuer_name") or ""
    holder_id = payload.get("holder_id") or ""
    holder = session.get(Investor, holder_id)
    if holder is None:
        raise HTTPException(
            status_code=409,
            detail=f"Investor {holder_id!r} no longer exists -- create it "
            "and resubmit the proposal",
        )

    security, security_created = _provisional_security(
        session, issuer_name, payload.get("security_name"),
        payload.get("share_count"),
    )
    # document_date is stored in the payload as an ISO string; the event
    # column is a real DateTime, so parse it back (never store a string in a
    # datetime column -- SQLite would fail to coerce it on later reads).
    raw_date = payload.get("document_date")
    effective = datetime.fromisoformat(raw_date) if raw_date else _utcnow()
    event = CapTableEvent(
        id=str(uuid4()),
        security_id=security.id,
        event_type=CapTableEventType.ISSUANCE,
        holder_id=holder.id,
        quantity=payload.get("share_count"),
        price_per_share=payload.get("price_per_share"),
        effective_date=effective,
        notes=f"From document {proposal.document_id}, approved by {reviewer.strip()}",
    )
    session.add(event)
    proposal.status = ProposalStatus.APPROVED
    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001 -- surfaced as a real 409, not a 500
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.refresh(event)

    # Write-time consistency check, exactly like the manual event endpoint:
    # a proposal can never push the log into an inconsistent state.
    try:
        compute_cap_table(session, issuer_name)
    except CapTableError as exc:
        session.delete(event)
        if security_created:
            session.delete(security)
        proposal.status = ProposalStatus.PROPOSED
        session.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.add(LedgerEntry(
        id=str(uuid4()),
        entry_type=LedgerEntryType.CAP_TABLE_EVENT,
        instrument_id=proposal.instrument_id,
        document_id=proposal.document_id,
        payload={
            "event": "cap_table_proposal_approved",
            "proposal_id": proposal.id,
            "cap_table_event_id": event.id,
            "security_id": security.id,
            "holder_id": holder.id,
            "share_count": payload.get("share_count"),
            "reviewer": reviewer.strip(),
        },
    ))
    session.commit()
    return event


@app.post(
    "/cap-table-proposals/{proposal_id}/link-investor",
    response_model=CapTableProposalOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def link_investor_to_proposal(
    proposal_id: str,
    investor_id: str,
    reviewer: str = "",
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapTableProposal:
    """Resolve an unresolved subscriber: attach a REAL investor to a pending
    proposal. This is the remedy the approval gate's 409 message promises --
    extraction can transcribe a subscriber the document names, but when the
    document only carries a signature block, the human decides *who* this
    position belongs to, and the cap table only ever issues to an investor
    row that exists. Only a PROPOSED (undecided) proposal can be edited;
    the link (and who did it) lands in the audit ledger."""
    proposal = session.get(CapTableProposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal {proposal_id!r} not found"
        )
    if proposal.status != ProposalStatus.PROPOSED:
        raise HTTPException(
            status_code=409,
            detail=f"Proposal {proposal_id!r} is {proposal.status.value}, "
            "not proposed -- it was already decided",
        )
    investor = session.get(Investor, investor_id)
    if investor is None:
        raise HTTPException(
            status_code=404, detail=f"Investor {investor_id!r} not found"
        )

    payload = dict(proposal.payload or {})
    previous_name = payload.get("holder_name")
    payload["holder_id"] = investor.id
    payload["holder_name"] = investor.name
    payload["subscriber_unresolved"] = False
    payload["investor_linked"] = {
        "investor_id": investor.id,
        "investor_name": investor.name,
        "previous_holder_name": previous_name,
        "reviewer": reviewer.strip() or None,
    }
    # Reassign the whole dict: in-place mutation of a JSON column is not
    # detected by SQLAlchemy's change tracking.
    proposal.payload = payload
    session.add(LedgerEntry(
        id=str(uuid4()),
        entry_type=LedgerEntryType.CAP_TABLE_PROPOSAL,
        instrument_id=proposal.instrument_id,
        document_id=proposal.document_id,
        payload={
            "event": "cap_table_proposal_investor_linked",
            "proposal_id": proposal.id,
            "investor_id": investor.id,
            "investor_name": investor.name,
            "previous_holder_name": previous_name,
            "reviewer": reviewer.strip() or None,
        },
    ))
    session.commit()
    session.refresh(proposal)
    return proposal


@app.get(
    "/cap-table-proposals",
    response_model=list[CapTableProposalOut],
    responses={401: {"model": ErrorOut}, 400: {"model": ErrorOut}},
)
def list_cap_table_proposals(
    status: str | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[CapTableProposal]:
    """Review queue for the human approval gate (newest first).

    ``?status=proposed`` shows only the pending decisions; omit it to see
    recent approvals/rejections as well. This is what the UI's proposals
    panel renders -- a proposal only ever becomes shares when a named human
    approves it, so this queue is the single place to see what awaits."""
    stmt = select(CapTableProposal)
    if status:
        try:
            status_enum = ProposalStatus(status.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown status {status!r} "
                "(use proposed, approved, or rejected)",
            ) from exc
        stmt = stmt.where(CapTableProposal.status == status_enum)
    stmt = stmt.order_by(CapTableProposal.created_at.desc()).limit(100)
    return list(session.execute(stmt).scalars().all())


@app.post(
    "/cap-table-proposals/{proposal_id}/reject",
    response_model=CapTableProposalOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def reject_cap_table_proposal(
    proposal_id: str,
    reviewer: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapTableProposal:
    """The other half of the human gate. A named reviewer rejects the
    proposal: nothing is written to the cap table, the proposal is marked
    REJECTED, and the decision lands in the audit ledger. A rejected
    proposal can never be approved afterwards -- the path forward is a new
    proposal from a corrected document."""
    proposal = session.get(CapTableProposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal {proposal_id!r} not found"
        )
    if proposal.status != ProposalStatus.PROPOSED:
        raise HTTPException(
            status_code=409,
            detail=f"Proposal {proposal_id!r} is {proposal.status.value}, "
            "not proposed -- it was already decided",
        )
    if not reviewer or not reviewer.strip():
        raise HTTPException(status_code=409, detail="A named reviewer is required")
    proposal.status = ProposalStatus.REJECTED
    session.add(LedgerEntry(
        id=str(uuid4()),
        entry_type=LedgerEntryType.CAP_TABLE_PROPOSAL,
        instrument_id=proposal.instrument_id,
        document_id=proposal.document_id,
        payload={
            "event": "cap_table_proposal_rejected",
            "proposal_id": proposal.id,
            "reviewer": reviewer.strip(),
        },
    ))
    session.commit()
    session.refresh(proposal)
    return proposal


# --------------------------------------------------------------------------- #
# Capital calls -- approval parity (Phase A)
#
# Mirrors the cap-table proposal gate: an extracted call is PENDING_APPROVAL
# until a named human reviewer approves it. funder_id is resolved against the
# Investor registry at creation; a call whose funder could not be resolved
# (no Investor row / no name) is flagged for manual review and approval of an
# unresolved call blocks with 409. Rejects never write event facts.
# --------------------------------------------------------------------------- #


capital_call_out_schema = CapitalCallOut

# Half-a-cent tolerance for float money comparisons: a payment within this
# distance of the remaining balance closes the call exactly once, and float
# noise from summing 500000.00 + 250000.005-style rows cannot flip a state.
_PAYMENT_TOLERANCE = 0.005


def derive_payment_status(amount_due: float, total_paid: float) -> str:
    """unpaid / partial / paid, derived -- the single definition the API
    exposes so no client recomputes it differently."""
    if total_paid <= 0:
        return "unpaid"
    if total_paid + _PAYMENT_TOLERANCE >= amount_due:
        return "paid"
    return "partial"


def _payment_sums(
    session: Session, call_ids: set[str]
) -> dict[str, float]:
    """One grouped query for the whole page of calls -- never one per row."""
    if not call_ids:
        return {}
    rows = session.execute(
        select(
            CapitalCallPayment.capital_call_id,
            func.coalesce(func.sum(CapitalCallPayment.amount), 0.0),
        )
        .where(CapitalCallPayment.capital_call_id.in_(call_ids))
        .group_by(CapitalCallPayment.capital_call_id)
    ).all()
    return {row[0]: float(row[1]) for row in rows}


def _capital_calls_out(
    session: Session, calls: list[CapitalCall]
) -> list[CapitalCallOut]:
    """Shape calls for the read side: attach each funder's registry name so a
    queue card can show *who* owes instead of an opaque ``funder_id`` UUID.

    The name is never stored on the call row -- the FK is the source of truth,
    so renames stay correct. One batched lookup for the whole page, never one
    query per row. A ``funder_id`` whose Investor row has since vanished yields
    ``funder_name=None`` while ``funder_id`` stays set: the client can flag
    that honestly instead of pretending the link is intact.

    Phase C: also derives reconciliation state (total_paid / remaining /
    payment_status) from the payment rows in the same batched style.
    """
    ids = {c.funder_id for c in calls if c.funder_id}
    names: dict[str, str] = {}
    if ids:
        rows = session.execute(
            select(Investor.id, Investor.name).where(Investor.id.in_(ids))
        ).all()
        names = {row[0]: row[1] for row in rows}

    paid_by_call = _payment_sums(session, {c.id for c in calls})

    outs = []
    for c in calls:
        out = CapitalCallOut.model_validate(c)
        out.funder_name = names.get(c.funder_id) if c.funder_id else None
        paid = paid_by_call.get(c.id, 0.0)
        out.total_paid = paid
        out.remaining = max(0.0, c.amount_due - paid)
        out.payment_status = derive_payment_status(c.amount_due, paid)
        outs.append(out)
    return outs


@app.post(
    "/instruments/{instrument_id}/capital-calls",
    response_model=capital_call_out_schema,
    status_code=201,
    responses={401: {"model": ErrorOut}},
)
def create_capital_call(
    instrument_id: str,
    payload: CapitalCallCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapitalCallOut:
    """Create a capital call notice (extracted data) pending approval.

    The funder_name is matched against the Investor registry by name; if found,
    the funder_id is resolved at creation time. If not found, funder_id stays
    NULL and the call is flagged ``funder_unresolved`` -- the reviewer is told
    to create the investor before approving (same semantics as the
    ``subscriber_unresolved`` flag on cap-table proposals).
    """
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {instrument_id!r} not found")

    funder_id: str | None = None
    funder_name: str | None = payload.funder_name
    if funder_name:
        resolved = session.execute(
            select(Investor).where(Investor.name == funder_name)
        ).scalars().first()
        if resolved is not None:
            funder_id = resolved.id

    call = CapitalCall(
        id=str(uuid4()),
        instrument_id=instrument_id,
        funder_id=funder_id,
        capital_owing=payload.capital_owing,
        currency=payload.currency[:3],
        amount_due=payload.capital_owing,
        due_date=payload.due_date,
        wire_details=payload.wire_details,
        source_text=payload.source_text or "",
        status=CapitalCallStatus.PENDING_APPROVAL,
        requires_manual_review=funder_id is None,
    )
    session.add(call)
    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.refresh(call)
    return _capital_calls_out(session, [call])[0]


@app.post(
    "/capital-calls/{call_id}/review",
    response_model=CapitalCallOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def review_capital_call(
    call_id: str,
    payload: CapitalCallReviewRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> CapitalCallOut:
    """Named-reviewer approve/reject gate for a capital call.

    Mirrors the cap-table proposal gate: a call is PENDING_APPROVAL until
    a human reviewer confirms it. Rejects write a ledger entry but no cap-table
    event -- capital calls track cash obligations, not ownership facts.

    A fully unresolved funder (no Investor row at all) blocks approval with
    409. A PROVISIONAL investor (created by the system from a name-match) is
    linkable -- the reviewer sees the flag and decides.
    """
    call = session.get(CapitalCall, call_id)
    if call is None:
        raise HTTPException(
            status_code=404, detail=f"Capital call {call_id!r} not found"
        )
    if call.status != CapitalCallStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Capital call {call_id!r} is {call.status.value}, "
                "not pending_approval -- a call is reviewed at most once"
            ),
        )
    reviewer = payload.reviewer.strip()
    if not reviewer:
        raise HTTPException(status_code=409, detail="A named reviewer is required")

    if payload.action == "approve":
        if call.funder_id is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The capital call has no resolved funder (funder_id is NULL) -- "
                    "create the investor and re-link before approving"
                ),
            )
        call.status = CapitalCallStatus.APPROVED
        event_type = LedgerEntryType.CAPITAL_CALL_REVIEW
        event_detail = "capital_call_approved"
    else:
        call.status = CapitalCallStatus.REJECTED
        event_type = LedgerEntryType.CAPITAL_CALL_REVIEW
        event_detail = "capital_call_rejected"

    session.add(
        LedgerEntry(
            id=str(uuid4()),
            entry_type=event_type,
            instrument_id=call.instrument_id,
            payload={
                "event": event_detail,
                "capital_call_id": call.id,
                "funder_id": call.funder_id,
                "capital_owing": call.capital_owing,
                "reviewer": reviewer,
                "action": payload.action,
            },
        )
    )
    session.commit()
    session.refresh(call)
    return _capital_calls_out(session, [call])[0]


@app.get(
    "/capital-calls",
    response_model=list[CapitalCallOut],
    responses={401: {"model": ErrorOut}},
)
def list_capital_calls(
    status_filter: CapitalCallStatus | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[CapitalCallOut]:
    """Review queue for capital calls.

    ``?status=`` filters to a single lifecycle state (e.g. ``pending_approval``
    for the call queue). Omit the filter to see all calls across all states.
    Each call carries ``funder_name`` resolved from the registry at read time.
    """
    stmt = select(CapitalCall)
    if status_filter is not None:
        stmt = stmt.where(CapitalCall.status == status_filter)
    stmt = stmt.order_by(CapitalCall.created_at.desc())
    rows = session.execute(stmt).scalars().all()
    return _capital_calls_out(session, list(rows))


@app.get(
    "/capital-calls/overdue",
    response_model=list[CapitalCallOut],
    responses={401: {"model": ErrorOut}},
)
def list_overdue_capital_calls(
    as_of: datetime | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[CapitalCallOut]:
    """Calls whose ``due_date`` has passed and that are still ``PENDING_APPROVAL``.

    ``?as_of=`` lets the caller evaluate overdue-ness against an arbitrary point
    in time (useful for backfill / reconciliation). Defaults to *now*.
    """
    cutoff = as_of or datetime.now(timezone.utc)
    rows = session.execute(
        select(CapitalCall)
        .where(CapitalCall.due_date < cutoff)
        .where(CapitalCall.status == CapitalCallStatus.PENDING_APPROVAL)
        .order_by(CapitalCall.due_date.asc())
    ).scalars().all()
    return _capital_calls_out(session, list(rows))


# --------------------------------------------------------------------------- #
# Capital-call payments -- Phase C reconciliation
#
# Matching money against an APPROVED call. Record-keeping only: the system
# never moves money and never silently absorbs extra cash (overpayment is a
# 409, never a write). Reconciled state (unpaid/partial/paid) is derived at
# read time from sum(payments) vs amount_due -- see _capital_calls_out.
# --------------------------------------------------------------------------- #


@app.get(
    "/capital-calls/{call_id}/payments",
    response_model=list[PaymentOut],
    responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}},
)
def list_capital_call_payments(
    call_id: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[PaymentOut]:
    """Payments recorded against a capital call, oldest first."""
    call = session.get(CapitalCall, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Capital call {call_id!r} not found")
    rows = session.execute(
        select(CapitalCallPayment)
        .where(CapitalCallPayment.capital_call_id == call_id)
        .order_by(CapitalCallPayment.paid_date.asc())
    ).scalars().all()
    return [PaymentOut.model_validate(p) for p in rows]


@app.post(
    "/capital-calls/{call_id}/payments",
    response_model=PaymentOut,
    status_code=201,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def record_capital_call_payment(
    call_id: str,
    payload: PaymentCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> PaymentOut:
    """Record a payment received against an APPROVED capital call.

    Gates: the call must exist (404) and be ``approved`` (409) -- payment on
    a pending or rejected call is refused, the money story follows the
    approval story. The payment may not exceed the call's remaining balance
    (409): extra cash is never silently absorbed, a real overpayment needs a
    human to look at the bank statement and act deliberately. Currency must
    match the call's currency (409) -- no implicit FX in the ledger.
    """
    call = session.get(CapitalCall, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Capital call {call_id!r} not found")
    if call.status != CapitalCallStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"Capital call {call_id!r} is {call.status.value}, "
            "not approved -- payments can only be recorded against approved calls",
        )
    recorded_by = payload.recorded_by.strip()
    if not recorded_by:
        raise HTTPException(status_code=409, detail="A named recorder is required")
    if payload.currency.upper() != call.currency.upper():
        raise HTTPException(
            status_code=409,
            detail=f"Payment currency {payload.currency!r} does not match "
            f"the call's currency {call.currency!r}",
        )

    paid = session.execute(
        select(func.coalesce(func.sum(CapitalCallPayment.amount), 0.0)).where(
            CapitalCallPayment.capital_call_id == call_id
        )
    ).scalar_one()
    remaining = call.amount_due - float(paid)
    if payload.amount > remaining + _PAYMENT_TOLERANCE:
        raise HTTPException(
            status_code=409,
            detail=f"Payment of {payload.amount} {payload.currency} exceeds the "
            f"remaining {remaining:.2f} {call.currency} on call {call_id!r} -- "
            "overpayments are rejected, never absorbed",
        )

    payment = CapitalCallPayment(
        id=str(uuid4()),
        capital_call_id=call_id,
        amount=payload.amount,
        currency=call.currency.upper(),
        paid_date=payload.paid_date,
        reference=payload.reference,
        recorded_by=recorded_by,
    )
    session.add(payment)
    session.add(
        LedgerEntry(
            id=str(uuid4()),
            entry_type=LedgerEntryType.CAPITAL_CALL_PAYMENT,
            instrument_id=call.instrument_id,
            payload={
                "event": "capital_call_payment_recorded",
                "capital_call_id": call_id,
                "amount": payload.amount,
                "currency": call.currency.upper(),
                "paid_date": payload.paid_date.isoformat(),
                "reference": payload.reference,
                "recorded_by": recorded_by,
            },
        )
    )
    session.commit()
    session.refresh(payment)
    return PaymentOut.model_validate(payment)


# --------------------------------------------------------------------------- #
# Transfer rules / ROFR engine -- Phase D governance gate
#
# Rules are prepared governance; a named human disposes. The engine
# (app.transfer_rules) evaluates every proposed TRANSFER against the
# issuer's active rules before the event reaches the append-only log;
# these routes manage the rules, the review queue, and the named-human
# resolution. See PHASE-D-TRANSFER-RULES.md.
# --------------------------------------------------------------------------- #


@app.post(
    "/transfer-rules",
    response_model=TransferRuleOut,
    status_code=201,
    responses={
        401: {"model": ErrorOut},
        400: {"model": ErrorOut},
    },
)
def create_transfer_rule(
    payload: TransferRuleCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> TransferRule:
    """Create a governance rule scoped to an issuer. 400 on an unknown
    rule_type or a malformed condition bag -- a broken rule must never
    reach the evaluation loop (the engine fails closed on unparseable
    conditions at evaluation time, but garbage is stopped at the door)."""
    condition = dict(payload.condition or {})
    if payload.window_days is not None:
        # The top-level window field rides into the validated condition bag
        # so it is persisted with the rule and visible in every audit row.
        condition["window_days"] = payload.window_days
    try:
        condition = validate_rule_condition(payload.rule_type, condition)
    except TransferRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Supersession: a new rule of the same type for the same issuer replaces
    # the previous active one (governance history stays interpretable -- the
    # old row is deactivated, never deleted).
    stale_rules = (
        session.execute(
            select(TransferRule)
            .where(TransferRule.issuer_name == payload.issuer_name)
            .where(
                TransferRule.rule_type == TransferRuleType(payload.rule_type)
            )
            .where(TransferRule.active.is_(True))
        )
        .scalars()
        .all()
    )
    for stale in stale_rules:
        stale.active = False

    rule = TransferRule(
        id=str(uuid4()),
        issuer_name=payload.issuer_name,
        rule_type=TransferRuleType(payload.rule_type),
        condition=condition,
        gate=TransferGate(payload.gate),
        approver=payload.approver,
        escalation_role=payload.escalation_role,
        escalation_after_days=payload.escalation_after_days,
        active=True,
        created_by=payload.created_by,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@app.get(
    "/transfer-rules",
    response_model=list[TransferRuleOut],
    responses={401: {"model": ErrorOut}},
)
def list_transfer_rules(
    issuer_name: str | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[TransferRuleOut]:
    """All rules (active and inactive -- history must stay interpretable),
    newest first, optionally scoped to one issuer."""
    query = select(TransferRule).order_by(TransferRule.created_at.desc())
    if issuer_name is not None:
        query = query.where(TransferRule.issuer_name == issuer_name)
    rows = session.execute(query).scalars().all()
    return [TransferRuleOut.model_validate(r) for r in rows]


def _evaluation_overdue(
    session: Session, evaluation: TransferEvaluation
) -> bool:
    """Derived, never stored (Phase B overdue-badge pattern): a PENDING
    evaluation is overdue when any triggering rule's escalation_after_days
    has elapsed since the evaluation was created."""
    if evaluation.outcome is not TransferEvaluationOutcome.PENDING:
        return False
    rule_ids = [
        r.get("rule_id")
        for r in (evaluation.rules_evaluated or [])
        if isinstance(r, dict) and r.get("rule_id")
    ]
    if not rule_ids:
        return False
    rules = (
        session.execute(select(TransferRule).where(TransferRule.id.in_(rule_ids)))
        .scalars()
        .all()
    )
    now = _utcnow()
    for rule in rules:
        if rule.escalation_after_days is None:
            continue
        created = evaluation.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if now - created > timedelta(days=rule.escalation_after_days):
            return True
    return False


@app.get(
    "/transfer-evaluations",
    response_model=list[TransferEvaluationOut],
    responses={401: {"model": ErrorOut}},
)
def list_transfer_evaluations(
    outcome: str | None = None,
    security_id: str | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> list[TransferEvaluationOut]:
    """Gate decisions, newest first. ``?outcome=pending`` is the review
    queue; every pending row carries its derived ``overdue`` flag so the
    UI never recomputes escalation differently from the server."""
    query = select(TransferEvaluation).order_by(
        TransferEvaluation.created_at.desc()
    )
    if outcome is not None:
        try:
            outcome_enum = TransferEvaluationOutcome(outcome)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown evaluation outcome {outcome!r}",
            ) from exc
        query = query.where(TransferEvaluation.outcome == outcome_enum)
    if security_id is not None:
        query = query.where(TransferEvaluation.security_id == security_id)
    rows = session.execute(query).scalars().all()
    return [
        TransferEvaluationOut(
            id=ev.id,
            security_id=ev.security_id,
            from_holder_id=ev.from_holder_id,
            holder_id=ev.holder_id,
            quantity=ev.quantity,
            price_per_share=ev.price_per_share,
            effective_date=ev.effective_date,
            rules_evaluated=ev.rules_evaluated or [],
            outcome=ev.outcome.value,
            blocking_rule_id=ev.blocking_rule_id,
            reviewer=ev.reviewer,
            reviewed_at=ev.reviewed_at,
            created_at=ev.created_at,
            overdue=_evaluation_overdue(session, ev),
        )
        for ev in rows
    ]


# --------------------------------------------------------------------------- #
# Transfer governance decisions (Phase D) -- resolving PENDING evaluations.   #
#                                                                             #
# Approve writes the pre-validated transfer event with the same overdraft     #
# replay check as the normal path; reject writes nothing. Both refuse an      #
# already-resolved evaluation (409) and require a named human reviewer.       #
# --------------------------------------------------------------------------- #


def _evaluation_out(
    session: Session, evaluation: TransferEvaluation
) -> TransferEvaluationOut:
    return TransferEvaluationOut(
        id=evaluation.id,
        security_id=evaluation.security_id,
        from_holder_id=evaluation.from_holder_id,
        holder_id=evaluation.holder_id,
        quantity=evaluation.quantity,
        price_per_share=evaluation.price_per_share,
        effective_date=evaluation.effective_date,
        rules_evaluated=evaluation.rules_evaluated or [],
        outcome=evaluation.outcome.value,
        blocking_rule_id=evaluation.blocking_rule_id,
        reviewer=evaluation.reviewer,
        reviewed_at=evaluation.reviewed_at,
        created_at=evaluation.created_at,
        overdue=_evaluation_overdue(session, evaluation),
    )


def _pending_evaluation_or_error(
    session: Session, evaluation_id: str
) -> TransferEvaluation:
    evaluation = session.get(TransferEvaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transfer evaluation {evaluation_id!r} not found",
        )
    if evaluation.outcome is not TransferEvaluationOutcome.PENDING:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Transfer evaluation already resolved as "
                    f"{evaluation.outcome.value}"
                ),
                "transfer_evaluation_id": evaluation.id,
                "outcome": evaluation.outcome.value,
            },
        )
    return evaluation


@app.post(
    "/transfer-evaluations/{evaluation_id}/approve",
    response_model=TransferEvaluationOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def approve_transfer_evaluation(
    evaluation_id: str,
    reviewer: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> TransferEvaluationOut:
    """Approve a PENDING evaluation and write its transfer event.

    The event is re-validated against the *current* ledger (overdraft
    replay), so shares that moved between proposal and decision are
    caught here, not silently written. On failure the event is rolled
    back and the evaluation stays PENDING for a corrected decision.
    """
    reviewer = reviewer.strip()
    if not reviewer:
        raise HTTPException(
            status_code=400, detail="reviewer must be a named human"
        )

    evaluation = _pending_evaluation_or_error(session, evaluation_id)
    security = session.get(SecurityModel, evaluation.security_id)
    if security is None:
        raise HTTPException(
            status_code=404,
            detail=f"Security {evaluation.security_id!r} not found",
        )

    event = CapTableEvent(
        id=str(uuid4()),
        security_id=evaluation.security_id,
        target_security_id=None,
        event_type=CapTableEventType.TRANSFER.value,
        holder_id=evaluation.holder_id,
        from_holder_id=evaluation.from_holder_id,
        quantity=evaluation.quantity,
        price_per_share=evaluation.price_per_share,
        effective_date=evaluation.effective_date,
        notes=f"Approved via transfer evaluation {evaluation.id} by {reviewer}",
    )
    session.add(event)
    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001 -- surfaced as a real 400, not a 500
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.refresh(event)

    # Same write-time consistency replay as record_cap_table_event.
    try:
        compute_cap_table(session, security.issuer_name)
    except CapTableError as exc:
        session.delete(event)
        session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    evaluation.outcome = TransferEvaluationOutcome.APPROVED
    evaluation.reviewer = reviewer
    evaluation.reviewed_at = _utcnow()
    session.add(
        LedgerEntry(
            id=str(uuid4()),
            entry_type=LedgerEntryType.TRANSFER_EVALUATION,
            payload={
                "event": "transfer_approved",
                "transfer_evaluation_id": evaluation.id,
                "cap_table_event_id": event.id,
                "security_id": evaluation.security_id,
                "from_holder_id": evaluation.from_holder_id,
                "to_holder_id": evaluation.holder_id,
                "quantity": evaluation.quantity,
                "reviewer": reviewer,
            },
        )
    )
    session.commit()
    session.refresh(evaluation)
    return _evaluation_out(session, evaluation)


@app.post(
    "/transfer-evaluations/{evaluation_id}/reject",
    response_model=TransferEvaluationOut,
    responses={
        401: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def reject_transfer_evaluation(
    evaluation_id: str,
    reviewer: str,
    session: Session = Depends(get_session),
    _: str = Depends(require_api_key),
) -> TransferEvaluationOut:
    """Reject a PENDING evaluation. Nothing is written to the cap table;
    the rejection itself is recorded on the evaluation and in the ledger."""
    reviewer = reviewer.strip()
    if not reviewer:
        raise HTTPException(
            status_code=400, detail="reviewer must be a named human"
        )

    evaluation = _pending_evaluation_or_error(session, evaluation_id)

    evaluation.outcome = TransferEvaluationOutcome.REJECTED
    evaluation.reviewer = reviewer
    evaluation.reviewed_at = _utcnow()
    session.add(
        LedgerEntry(
            id=str(uuid4()),
            entry_type=LedgerEntryType.TRANSFER_EVALUATION,
            payload={
                "event": "transfer_rejected",
                "transfer_evaluation_id": evaluation.id,
                "security_id": evaluation.security_id,
                "from_holder_id": evaluation.from_holder_id,
                "to_holder_id": evaluation.holder_id,
                "quantity": evaluation.quantity,
                "reviewer": reviewer,
            },
        )
    )
    session.commit()
    session.refresh(evaluation)
    return _evaluation_out(session, evaluation)


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    """Serve the React app for any unmatched route (SPA client-side routing)."""
    index = _static_dir / "index.html"
    return FileResponse(str(index))
