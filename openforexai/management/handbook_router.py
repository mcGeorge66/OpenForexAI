"""REST API for the personal knowledge base (handbook)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

_repository = None


def set_repository(repo: Any) -> None:
    global _repository
    _repository = repo


def _repo():
    if _repository is None:
        raise HTTPException(status_code=503, detail="Repository not available")
    return _repository


# ── Models ────────────────────────────────────────────────────────────────────

class DocCreate(BaseModel):
    title: str = "Untitled"
    content: str = ""
    is_folder: bool = False
    parent_id: str | None = None
    sort_order: int = 0
    tags: list[str] = []


class DocUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    parent_id: str | None = None
    is_folder: bool | None = None
    sort_order: int | None = None
    tags: list[str] | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/documents")
async def list_documents() -> list[dict]:
    return await _repo().kb_list_documents()


@router.post("/documents")
async def create_document(body: DocCreate) -> dict:
    doc_id = await _repo().kb_create_document(body.model_dump())
    return {"id": doc_id}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str) -> dict:
    doc = await _repo().kb_get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/documents/{doc_id}")
async def update_document(doc_id: str, body: DocUpdate) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await _repo().kb_update_document(doc_id, updates)
    return {"ok": True}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    await _repo().kb_delete_document(doc_id)
    return {"ok": True}


@router.get("/search")
async def search(q: str, limit: int = 20) -> list[dict]:
    if not q.strip():
        return []
    return await _repo().kb_search(q.strip(), limit=min(limit, 50))
