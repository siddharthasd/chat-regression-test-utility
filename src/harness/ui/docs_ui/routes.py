"""Documentation viewer routes — readable by all roles."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from harness.ui._context import ctx
from harness.ui._templates import templates

router = APIRouter()

_DOCS_DIR = Path(__file__).parents[4] / "docs"

_GUIDES: dict[str, tuple[str, str]] = {
    "about": ("about.md", "About the Harness"),
    "csv-upload": ("csv-upload-guide.md", "CSV Upload Guide"),
    "connector-developer-guide": ("connector-developer-guide.md", "Connector Developer Guide"),
    "evaluator-developer-guide": ("evaluator-developer-guide.md", "Evaluator Developer Guide"),
    "solution-architecture": ("solution-architecture.md", "Solution Architecture"),
}


@router.get("/docs/{guide}", name="docs_guide")
def docs_guide(request: Request, guide: str):
    entry = _GUIDES.get(guide)
    if entry is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    filename, title = entry
    try:
        content = (_DOCS_DIR / filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Guide file not found")
    return templates.TemplateResponse(
        request,
        "docs/guide.html",
        {"title": title, "markdown_content": content, **ctx(request)},
    )
