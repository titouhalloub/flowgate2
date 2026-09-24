# Serves API.md as raw markdown, and api-docs.html as a rendered page.
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse

router = APIRouter(tags=["docs"])
_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_MD = _REPO_ROOT / "API.md"
_API_HTML = _REPO_ROOT / "api-docs.html"


@router.get("/api-docs", response_class=HTMLResponse, include_in_schema=False)
def serve_api_docs_html() -> HTMLResponse:
    if not _API_HTML.exists():
        return HTMLResponse(
            "<h1>API documentation not found</h1>"
            "<p>api-docs.html is missing from the deployment.</p>",
            status_code=404,
        )
    return HTMLResponse(_API_HTML.read_text(encoding="utf-8"))


@router.get("/api-docs.md", response_class=PlainTextResponse, include_in_schema=False)
def serve_api_docs_md() -> PlainTextResponse:
    if not _API_MD.exists():
        return PlainTextResponse("# API documentation not found", status_code=404)
    return PlainTextResponse(
        _API_MD.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )
