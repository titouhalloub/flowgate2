"""Read-only help assistant for Flowgate.

Answers questions about how the app works, grounded in the repo's
markdown plans. Read-only by design -- it never writes, never executes an
action, and never claims a compliance decision. Its only outputs are an
answer string and a list of source citations.

The LLM call lives in ``_ask_llm`` so tests can monkeypatch it without
touching the network. Same discipline as ``app/classification.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


# Files loaded into the system prompt on first request and cached.
# Curated: the current architecture and the current feature set. Adding a
# file here adds its content to every request, so keep the list tight.
_KNOWLEDGE_FILES = [
    "AI-ASSISTANT-AND-COMPLIANCE-PLAN.md",
    "POSITIONING.md",
    "PHASE3-CONVERTIBLES-PLAN.md",
    "CAPITAL-CALL-PLAN.md",
    "CAPTABLE-ROADMAP-FEATURES.md",
]

_REPO_ROOT = Path(__file__).resolve().parent.parent

_knowledge_cache: str | None = None


def _load_knowledge_base() -> str:
    """Read the curated markdown files once and cache the concatenation.

    Missing files are skipped silently -- a plan that has been renamed or
    deleted should not 500 the assistant. The header marker in the output
    tells the model which file each block came from, so its citations can
    name the source.
    """
    global _knowledge_cache
    if _knowledge_cache is not None:
        return _knowledge_cache

    parts: list[str] = []
    for name in _KNOWLEDGE_FILES:
        path = _REPO_ROOT / name
        if not path.is_file():
            continue
        parts.append(f"# === {name} ===\n\n{path.read_text(encoding='utf-8')}")

    _knowledge_cache = "\n\n".join(parts)
    return _knowledge_cache


_SYSTEM_PROMPT = """
CRITICAL OUTPUT RULES: Output ONLY the final answer. No reasoning,
no analysis, no preamble, no step-by-step narration. Do not restate
the question. Do not explain what you are about to say. If the answer
is not in the provided context, say exactly: "I don't have that in my
knowledge base." Two sentences maximum.
You are the Flowgate Assistant. You answer questions \
about how the Flowgate application works -- its compliance engine, its \
cap-table model, its document pipeline, its convertibles and priced \
rounds, its capital calls, its vesting and 409A features.

You answer ONLY from the reference documents below. If a question is not \
covered there, say so directly: "I don't have information about that in \
the app." Do not improvise. Do not use general knowledge. Do not invent \
features.

You NEVER:
- claim a document is compliant or non-compliant
- say a proposal, conversion, or valuation should be approved
- suggest executing an action; describe the click the user should make
- answer questions about other software products
- give investment, tax, or legal advice

You ALWAYS:
- cite the reference document that supports your answer
- say "I don't have information about that" when the answer is not in the \
reference documents
- keep answers under 120 words unless the user asks for detail

Return valid JSON with this shape:
{"answer": "<the answer>", "sources": ["<filename1>", "<filename2>"]}

Reference documents:

{knowledge}
"""


def _ask_llm(system: str, user: str) -> str:
    """The only network call in this module. Tests monkeypatch this.

    Uses the same OpenAI-compatible client pattern as classification.py
    (which supports both Anthropic and OpenRouter via base_url). One
    retry on empty response; no retry on exception -- the caller handles
    that.
    """
    from openai import OpenAI

    pref = settings.llm_backend_preference
    if pref == "anthropic" and settings.anthropic_api_key:
        api_key = settings.anthropic_api_key
        base_url = "https://api.anthropic.com/v1"
        model = settings.anthropic_model
    elif settings.openrouter_api_key:
        api_key = settings.openrouter_api_key
        base_url = settings.openrouter_base_url
        model = settings.openrouter_assistant_model
    elif settings.anthropic_api_key:
        api_key = settings.anthropic_api_key
        base_url = "https://api.anthropic.com/v1"
        model = settings.anthropic_model
    else:
        raise RuntimeError("No LLM API key configured for the assistant.")

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=55.0)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=512,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = resp.choices[0].message.content.strip() if resp.choices else ""
    if not raw or raw.lower() in ("{}", "null"):
        resp = client.chat.completions.create(
            model=model,
            max_tokens=512,
            temperature=0.0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = resp.choices[0].message.content.strip() if resp.choices else ""
    return raw


def ask_assistant(question: str, issuer_name: str | None = None) -> dict[str, Any]:
    """Public entry point. Returns {"answer": str, "sources": list[str]}.

    ``issuer_name`` is accepted but unused in v1 -- a placeholder for the
    Phase 4.1 enhancement that injects the current cap table into context.
    """
    knowledge = _load_knowledge_base()
    if not knowledge:
        return {
            "answer": "The knowledge base is empty. No reference documents "
                      "were found in the repository.",
            "sources": [],
        }

    system = _SYSTEM_PROMPT.replace("{knowledge}", knowledge)
    # Keep the question short and self-contained. No issuer context yet.
    user = question.strip()[:2000]

    try:
        raw = _ask_llm(system, user)
    except Exception:
        # Degrade gracefully. Same pattern as the classification fallback.
        return {
            "answer": "I couldn't reach the language model. Please try again "
                      "in a moment.",
            "sources": [],
        }

    try:
        payload = json.loads(raw)
        answer = str(payload.get("answer", "")).strip()
        sources = payload.get("sources", [])
        if not isinstance(sources, list):
            sources = []
        sources = [str(s) for s in sources if isinstance(s, str)]
    except (json.JSONDecodeError, AttributeError):
        # The model didn't return JSON. Fall back to raw text with no
        # citations rather than failing the request.
        answer = raw.strip() or "I couldn't produce an answer for that."
        sources = []

    if not answer:
        answer = "I couldn't produce an answer for that."

    return {"answer": answer, "sources": sources}
