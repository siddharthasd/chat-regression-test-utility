"""Headless connector discovery endpoint (020, FR-001)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from harness.connector.registry import ConnectorRegistryReader
from harness.persistence import get_session
from harness.ui.api.auth import require_api_auth
from harness.ui.api.schemas import ConnectorListItem

router = APIRouter()


@router.get("/connectors")
def list_connectors(user: dict = Depends(require_api_auth)) -> dict:
    """Return all registered, active connectors (no per-user filtering)."""
    with get_session() as session:
        entries = ConnectorRegistryReader(session).list_active()
    return {
        "connectors": [
            ConnectorListItem(
                id=e.connector_id,
                name=e.display_name,
                description=e.description,
            ).model_dump()
            for e in entries
        ]
    }
