# Serves API.md as raw markdown.
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["docs"])
_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_MD = _REPO_ROOT / "API.md"


@router.get("/api-docs.md", response_class=PlainTextResponse, include_in_schema=False)
def serve_api_docs_md() -> PlainTextResponse:
    if not _API_MD.exists():
        return PlainTextResponse("# API documentation not found", status_code=404)
    return PlainTextResponse(
        _API_MD.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )
