"""Phase 5 orchestration — one pipeline, configurable compliance, ledger."""

from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy.orm import Session

from app.classification import classify_document
from app.compliance import ComplianceGateway
from app.extraction import run_extraction
from app.models.enums import (
    DocumentStatus,
    DocumentType,
    IngestionSource,
    LedgerEntryType,
    ShariahContractType,
    ShariahReviewStatus,
    TransactionType,
)
from app.models.orm import Document, Instrument, LedgerEntry
from app.telemetry import get_tracer


class PipelineResult:
    def __init__(
        self,
        document,
        class_conf,
        extract_conf,
        outcome,
        routed,
        extracted_fields=None,
        compliance_findings=None,
    ):
        self.document = document
        self.classconf = class_conf
        self.extractconf = extract_conf
        self.outcome = outcome
        self.routed = routed
        # Frontend-facing lists. Empty on routed/aborted paths; populated
        # on the processed path so the UI can render without a second call.
        self.extracted_fields = extracted_fields or []
        self.compliance_findings = compliance_findings or []

    def __repr__(self):
        return (f"<PipelineResult doc={self.document.id} "
                f"type={self.document.document_type.value} "
                f"compliance={self.outcome}>")


_DOC_TYPE_TO_TRANSACTION_TYPE: dict[DocumentType, TransactionType] = {
    DocumentType.LOAN_AGREEMENT: TransactionType.LOAN,
    DocumentType.TERM_SHEET: TransactionType.LOAN,
    DocumentType.SUKUK_CERTIFICATE: TransactionType.SUKUK,
    DocumentType.CAPITAL_CALL_NOTICE: TransactionType.FUND_INTEREST,
    DocumentType.SUBSCRIPTION_AGREEMENT: TransactionType.FUND_INTEREST,
    DocumentType.EQUITY_SUBSCRIPTION: TransactionType.EQUITY,
    DocumentType.SHA: TransactionType.EQUITY,
}


def _backfill_deal_container(
    instrument: Instrument,
    classification: ClassificationResult,
    extracted_data: dict | None,
) -> None:
    """Carry the deal fields the pipeline read from the document onto the instrument.

    The instrument is created by the caller as a container (often with placeholder
    values like "Demo Issuer" / 1,000,000 USD ). Once extraction has read the
    actual document, those creation-time placeholders must not keep shadowing
    what the document actually says. Every write is guarded: a doc that lacks a
    field never blanks a real one, and nothing is written when extraction failed..
    """
    data = (extracted_data or {}).get("data", {})
    for key in ("issuer_name", "funder_name", "fund_name", "company_name"):
        if data.get(key):
            instrument.issuer_name = data[key]
            break
    for key in (
        "purchase_amount",
        "principal_amount",
        "total_size",
        "commitment_amount",
        "capital_owing",
        "purchase_price",
        "total_offering_amount",
    ):
        amount = data.get(key)
        if amount is not None:
            instrument.amount = amount
            break
    if data.get("currency"):
        instrument.currency = data["currency"]

    # The classified document type is already past the 0.75 confidence gate
    # here (UNCLASSIFIED returned earlier in process_document), so correcting
    # the container's transaction type is safe and never a guess.
    txn = _DOC_TYPE_TO_TRANSACTION_TYPE.get(classification.document_type)
    if txn is not None:
        instrument.transaction_type = txn


def _normalise_raw_text(text: str) -> str:
    """Normalise raw text so every downstream regex sees one canonical form.

    Three real-world document quirks this handles:

    1. Smart quotes. Curly apostrophes (U+2018 / U+2019) and curly double
       quotes (U+201C / U+201D) break character classes tuned for straight
       ASCII. Every name-capture regex in app/extraction.py uses a class
       like [A-Za-z0-9 .,&"'-], which terminates on a curly apostrophe.
       A name like "Reed's Inc." (curly) captured as "Reed" or as
       "s Inc." depending on which pattern matched first.

    2. LaTeX math delimiters. PDFs generated from LaTeX or Clerky templates
       often carry literal \\( \\) \\[ \\] sequences in the extracted text
       layer. These break every money regex because the $ that should
       precede a number is not there. Replacing them with a space
       preserves word boundaries.

    3. Multiple consecutive spaces. Collapsed to a single space so window-
       based matchers (the money helpers use fixed character windows) do
       not miss a keyword that sits just past a run of whitespace.

    Applied once, at the top of process_document. Every ingestion path
    (paste-text, upload, OCR) converges here.
    """
    if not text:
        return text
    # Smart quotes -> straight ASCII
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # LaTeX math delimiters -> single space (preserves word boundaries)
    text = re.sub(r"\\[\(\)\[\]]", " ", text)
    # Collapse runs of spaces and tabs
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text



def _guess_type_from_filename(filename: str) -> DocumentType | None:
    """Best-effort document type guess from the filename.

    Used to rescue an UNCLASSIFIED verdict: if the extractor produces
    confident verified fields on the guessed type, the guess is proven
    and the classifier's uncertainty is moot.
    """
    name = (filename or "").lower()
    if "safe" in name:
        return DocumentType.SAFE
    if "sukuk" in name:
        return DocumentType.SUKUK_CERTIFICATE
    if "equity" in name and "subscription" in name:
        return DocumentType.EQUITY_SUBSCRIPTION
    if "subscription" in name:
        return DocumentType.SUBSCRIPTION_AGREEMENT
    if "capital" in name and "call" in name:
        return DocumentType.CAPITAL_CALL_NOTICE
    if "term" in name and "sheet" in name:
        return DocumentType.TERM_SHEET
    if "loan" in name:
        return DocumentType.LOAN_AGREEMENT
    return None


def _replace_classification(cls_obj, doc_type, confidence):
    """Return a copy of a classification result with the given fields.

    Handles dataclasses (frozen or not) and plain mutable objects.
    """
    import dataclasses
    if dataclasses.is_dataclass(cls_obj) and not isinstance(cls_obj, type):
        return dataclasses.replace(
            cls_obj, document_type=doc_type, confidence=confidence,
        )
    cls_obj.document_type = doc_type
    cls_obj.confidence = confidence
    return cls_obj


def process_document(session: Session, instrument: Instrument,
                     gateway: ComplianceGateway, text: str,
                     filename: str = "document.txt",
                     file_url: str | None = None,
                     extra_jurisdictions: list[str] | None = None) -> PipelineResult:
    """Classify -> extract -> compliance gate -> ledger, one transaction.

    file_url: where the uploaded original was persisted (uploads/...).
    None keeps the historical "mem://" placeholder used by text submissions.
    """
    text = _normalise_raw_text(text)

    def make_doc(doc_type, class_conf, extract_conf, source, status):
        return Document(
            id=str(uuid4()),
            instrument_id=instrument.id,
            filename=filename,
            file_url=file_url or ("mem://" + uuid4().hex),
            document_type=doc_type,
            classification_confidence=class_conf,
            extraction_confidence=extract_conf,
            ingestion_source=source,
            compliance_mode=instrument.compliance_mode,
            status=status,
        )

    def ledger(doc, stage, payload):
        session.add(LedgerEntry(
            id=str(uuid4()),
            entry_type=LedgerEntryType.DOCUMENT_RESULT,
            instrument_id=instrument.id,
            document_id=doc.id,
            payload={**payload, "stage": stage},
        ))

    trace = get_tracer().span("pipeline.run",
                              instrument_id=instrument.id,
                              compliance_mode=instrument.compliance_mode.value)

    # 1. Classification: its own step, confidence gate, never a guess.
    # Pass the filename too — a file named "Subscription-Agreement-...pdf"
    # is a strong signal even when the OCR'd text is sparse or partial.
    classification = classify_document(text, filename=filename)

    # Rescue: if the classifier bailed, try a filename-derived guess.
    # The extractor is the stronger oracle: if it produces confident
    # verified fields on the guess, the classification was right.
    _rescued_outcome = None
    if classification.document_type == DocumentType.UNCLASSIFIED:
        _guess = _guess_type_from_filename(filename)
        if _guess is not None:
            _candidate = run_extraction(text, _guess.value)
            if (_candidate is not None
                    and _candidate.extraction is not None
                    and not _candidate.routed_to_review):
                classification = _replace_classification(
                    classification, _guess,
                    max(0.75, _candidate.confidence),
                )
                _rescued_outcome = _candidate

    if classification.document_type == DocumentType.UNCLASSIFIED:
        doc = make_doc(DocumentType.UNCLASSIFIED, classification.confidence, 0.0,
                       IngestionSource.MANUAL_ENTRY, DocumentStatus.REVIEW_NEEDED)
        session.add(doc)
        session.flush()  # FK-order: document must exist before ledger rows reference it
        ledger(doc, "classification",
               {"outcome": "unclassified", "confidence": classification.confidence})
        session.commit()
        trace.finish({"status": "unclassified",
                      "confidence": classification.confidence})
        trace.emit()
        return PipelineResult(doc, classification.confidence, 0.0,
                              ShariahReviewStatus.NOT_APPLICABLE, True)

    # 2. Extraction: typed -> JSONB with schema name + version (gap #2).
    if _rescued_outcome is not None:
        outcome = _rescued_outcome
    else:
        outcome = run_extraction(text, classification.document_type.value)

    # The instrument container was created by the caller (often with placeholder
    # values); once extraction read the actual document, carry the deal fields
    # it found onto the instrument so the UI/showed deal container reflects the
    # document, not creation-time defaults. Done even when the extraction routed
    # to review (a valid extraction model still names the issuer/amount/currency).
    if outcome.extraction is not None:
        _backfill_deal_container(instrument, classification, outcome.extracted_data)

    if outcome.extraction is None or outcome.routed_to_review:
        doc = make_doc(classification.document_type, classification.confidence,
                       outcome.confidence, IngestionSource.NATIVE_EXTRACTION,
                       DocumentStatus.REVIEW_NEEDED)
        doc.extracted_data = outcome.extracted_data
        doc.error_message = outcome.error
        session.add(doc)
        session.flush()  # FK-order: document must exist before ledger rows reference it
        ledger(doc, "extraction",
               {"outcome": "review", "confidence": outcome.confidence,
                "schema": outcome.schema_name})
        session.commit()
        trace.finish({"status": "review", "confidence": outcome.confidence})
        trace.emit()
        return PipelineResult(doc, classification.confidence, outcome.confidence,
                              ShariahReviewStatus.NOT_APPLICABLE, True)

    # 3. Compliance gateway: same code path, rule set = configuration.
    doc = make_doc(classification.document_type, classification.confidence,
                   outcome.confidence, IngestionSource.NATIVE_EXTRACTION,
                   DocumentStatus.PROCESSED)
    doc.extracted_data = outcome.extracted_data
    session.add(doc)
    session.flush()  # FK-order: document must exist before ledger rows reference it

    prior_docs = session.query(Document).filter(
        Document.instrument_id == instrument.id,
        Document.id != doc.id,
    ).all()

    # Carry the extracted Shariah-relevant fields onto the instrument so the
    # compliance gateway evaluates the REAL extracted record — not a manually
    # pre-populated one. Without this, an otherwise-clean sukuk is wrongly
    # flagged noncompliant because contract type / asset backing never land on
    # the instrument, and (silently) any declared contract would not reach the
    # instrument either.
    data = (outcome.extracted_data or {}).get("data", {})
    contract = data.get("contract_type")
    if contract is not None:
        instrument.shariah_contract_type = ShariahContractType(contract)
    if data.get("asset_description"):
        instrument.underlying_asset_description = data["asset_description"]

    decision = gateway.evaluate(
        instrument,
        [doc, *prior_docs],
        extra_jurisdictions=extra_jurisdictions,
    )
    instrument.shariah_review_status = decision.outcome

    session.add(LedgerEntry(
        id=str(uuid4()),
        entry_type=LedgerEntryType.COMPLIANCE_EVENT,
        instrument_id=instrument.id,
        document_id=doc.id,
        payload={"event": "compliance_gateway",
                 "rule_set": decision.rule_set_name,
                 "outcome": decision.outcome.value,
                 "blocking": decision.blocking},
    ))
    session.commit()

    trace.finish({"status": "processed",
                  "outcome": decision.outcome.value})
    trace.emit()
    # Normalize the extraction into the frontend's {name, value} shape
    # and serialize the compliance findings so the UI can render both
    # without a second round-trip.
    _data = (outcome.extracted_data or {}).get("data", {}) if outcome.extracted_data else {}
    _fields = [
        {"name": k, "value": v}
        for k, v in _data.items()
        if k not in ("schema_name", "schema_version", "extracted_at", "source_text")
    ]
    _findings = []
    for _f in getattr(decision, "findings", []) or []:
        _sev = getattr(_f, "severity", None)
        _findings.append({
            "code": getattr(_f, "code", ""),
            "severity": _sev.value if hasattr(_sev, "value") else str(_sev or ""),
            "message": getattr(_f, "message", ""),
            "detail": getattr(_f, "detail", {}) or {},
        })

    result = PipelineResult(doc, classification.confidence, outcome.confidence,
                            decision.outcome, False,
                            extracted_fields=_fields,
                            compliance_findings=_findings)

    try:
        from app.webhooks import fire_pipeline_webhooks
        fire_pipeline_webhooks(session, instrument, result)
    except Exception:
        pass

    return result