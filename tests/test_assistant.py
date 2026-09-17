"""Assistant tests. Stub the LLM call so no network is involved."""

import json
import pytest

from app import assistant


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the module-level knowledge cache between tests."""
    assistant._knowledge_cache = None
    yield
    assistant._knowledge_cache = None


def test_knowledge_base_loads(monkeypatch):
    """The loader reads the curated markdown files and caches the result."""
    kb1 = assistant._load_knowledge_base()
    kb2 = assistant._load_knowledge_base()
    assert kb1  # non-empty
    assert kb1 is kb2  # cached
    # Every file that exists should have its header marker present
    for name in assistant._KNOWLEDGE_FILES:
        if (assistant._REPO_ROOT / name).is_file():
            assert f"# === {name} ===" in kb1


def test_assistant_returns_answer_and_sources(monkeypatch):
    """The happy path: valid JSON from the model is parsed correctly."""
    def fake_ask(system: str, user: str) -> str:
        assert "Reference documents" in system
        assert user == "What is a convertible?"
        return json.dumps({
            "answer": "A convertible is a SAFE held off the cap table.",
            "sources": ["PHASE3-CONVERTIBLES-PLAN.md"],
        })

    monkeypatch.setattr(assistant, "_ask_llm", fake_ask)
    result = assistant.ask_assistant("What is a convertible?")
    assert "SAFE held off the cap table" in result["answer"]
    assert result["sources"] == ["PHASE3-CONVERTIBLES-PLAN.md"]


def test_assistant_degrades_on_llm_error(monkeypatch):
    """If the model call raises, the assistant returns a friendly message
    rather than a 500."""
    def boom(system: str, user: str) -> str:
        raise RuntimeError("upstream down")

    monkeypatch.setattr(assistant, "_ask_llm", boom)
    result = assistant.ask_assistant("Any question")
    assert "couldn't reach the language model" in result["answer"]
    assert result["sources"] == []


def test_assistant_handles_non_json_response(monkeypatch):
    """If the model returns plain text instead of JSON, fall back to
    returning it as the answer with no citations."""
    def plain(system: str, user: str) -> str:
        return "A convertible is a SAFE held off the cap table."

    monkeypatch.setattr(assistant, "_ask_llm", plain)
    result = assistant.ask_assistant("What is a convertible?")
    assert "SAFE held off the cap table" in result["answer"]
    assert result["sources"] == []


def test_assistant_empty_knowledge_base(monkeypatch):
    """If no markdown files are found, refuse politely."""
    monkeypatch.setattr(assistant, "_KNOWLEDGE_FILES", [])
    assistant._knowledge_cache = None
    result = assistant.ask_assistant("Anything")
    assert "knowledge base is empty" in result["answer"].lower()


def test_endpoint_rejects_empty_question(client):
    """Empty questions are rejected by the Pydantic min_length."""
    r = client.post("/assistant/ask", json={"question": ""})
    assert r.status_code == 422


def test_endpoint_returns_answer_shape(client, monkeypatch):
    """Full HTTP path with a stubbed LLM."""
    def fake_ask(system: str, user: str) -> str:
        return json.dumps({
            "answer": "Test answer.",
            "sources": ["POSITIONING.md"],
        })

    monkeypatch.setattr(assistant, "_ask_llm", fake_ask)
    r = client.post(
        "/assistant/ask",
        json={"question": "What is Flowgate?", "issuer_name": None},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Test answer."
    assert body["sources"] == ["POSITIONING.md"]