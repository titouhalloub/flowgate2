"""Phase 2.5b -- build_context serialization.

The context is what JSON Logic conditions are evaluated against.
These tests pin the exact shape and the enum-to-string conversion.
"""

from app.compliance import build_context
from app.models.enums import (
    ComplianceMode,
    DocumentType,
    ShariahContractType,
    TransactionType,
)
from tests.conftest import make_document, make_instrument


def test_context_has_instrument_and_documents_keys():
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    ctx = build_context(instr, [])
    assert set(ctx.keys()) == {"instrument", "documents_by_type"}
    assert set(ctx["instrument"].keys()) == {
        "transaction_type",
        "compliance_mode",
        "shariah_contract_type",
        "underlying_asset_id",
        "underlying_asset_description",
        "type_specific_data",
    }


def test_enum_values_are_serialized_as_strings():
    instr = make_instrument(
        txn_type=TransactionType.SUKUK,
        mode=ComplianceMode.ISLAMIC,
        shariah_contract_type=ShariahContractType.MURABAHA,
    )
    ctx = build_context(instr, [])
    assert ctx["instrument"]["transaction_type"] == "sukuk"
    assert ctx["instrument"]["compliance_mode"] == "islamic"
    assert ctx["instrument"]["shariah_contract_type"] == "murabaha"


def test_nullable_shariah_contract_type_stays_none():
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    ctx = build_context(instr, [])
    assert ctx["instrument"]["shariah_contract_type"] is None


def test_type_specific_data_exposes_only_four_keys():
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={
            "interest_rate": 0.06,
            "fixed_coupon": False,
            "profit_rate": 0.05,
            "ijara_rental_rate": 0.04,
            "unrelated_key": "should not appear",
        },
    )
    ctx = build_context(instr, [])
    tsd = ctx["instrument"]["type_specific_data"]
    assert set(tsd.keys()) == {
        "interest_rate",
        "fixed_coupon",
        "profit_rate",
        "ijara_rental_rate",
    }
    assert tsd["interest_rate"] == 0.06
    assert "unrelated_key" not in tsd


def test_documents_grouped_by_document_type():
    instr = make_instrument(
        txn_type=TransactionType.SUKUK,
        mode=ComplianceMode.ISLAMIC,
    )
    docs = [
        make_document(instr, doc_type=DocumentType.FATWA),
        make_document(instr, doc_type=DocumentType.KYC),
        make_document(instr, doc_type=DocumentType.FATWA),
    ]
    ctx = build_context(instr, docs)
    assert set(ctx["documents_by_type"].keys()) == {"fatwa", "kyc"}
    assert len(ctx["documents_by_type"]["fatwa"]) == 2
    assert len(ctx["documents_by_type"]["kyc"]) == 1


def test_documents_are_serialized_with_id_only():
    instr = make_instrument(
        txn_type=TransactionType.SUKUK,
        mode=ComplianceMode.ISLAMIC,
    )
    docs = [make_document(instr, doc_type=DocumentType.FATWA)]
    ctx = build_context(instr, docs)
    entry = ctx["documents_by_type"]["fatwa"][0]
    assert set(entry.keys()) == {"id"}
    assert entry["id"] == docs[0].id


def test_empty_documents_yields_empty_dict():
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    ctx = build_context(instr, [])
    assert ctx["documents_by_type"] == {}


def test_context_feeds_json_logic_evaluator():
    """Integration with the evaluator: the context is directly
    consumable by a JSON Logic condition, no reshaping needed."""
    from app.json_logic import evaluate

    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    ctx = build_context(instr, [])

    # A condition shaped like the interest sanity rule
    condition = {
        "and": [
            {"!": {"empty": [
                {"var": "instrument.type_specific_data.interest_rate"},
            ]}},
            {"in_range": [
                {"var": "instrument.type_specific_data.interest_rate"},
                0.0, 0.30,
            ]},
        ]
    }
    assert evaluate(condition, ctx) is True

    # A condition that tests transaction_type against a literal
    assert evaluate(
        {"==": [{"var": "instrument.transaction_type"}, "loan"]},
        ctx,
    ) is True

    # A condition that tests document presence
    assert evaluate(
        {"empty": [{"var": "documents_by_type.kyc"}]},
        ctx,
    ) is True
