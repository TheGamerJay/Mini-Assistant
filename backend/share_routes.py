"""
share_routes.py
Public content sharing system for Mini Assistant AI.

Endpoints:
  POST /api/share          — create a share (authenticated)
  GET  /api/share/{id}     — fetch shared content (public, no auth)
  DELETE /api/share/{id}   — delete own share (authenticated)
"""

import logging
import time
import uuid
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger(__name__)

share_router = APIRouter(prefix="/api/share", tags=["share"])

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://www.miniassistantai.com")

# ---------------------------------------------------------------------------
# Auth helper (mirrors auth_routes.py pattern)
# ---------------------------------------------------------------------------
JWT_SECRET    = os.environ.get("JWT_SECRET", "mini_assistant_jwt_secret_2025")
JWT_ALGORITHM = "HS256"


def _decode_bearer(authorization: str | None) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        from jose import jwt
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = payload.get("sub")
        return payload if (uid and isinstance(uid, str)) else None
    except Exception:
        return None


async def _get_db():
    try:
        import server as _srv
        return _srv.db
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreateShareBody(BaseModel):
    content_type: str          # 'text' | 'app' | 'image'
    content: str               # markdown text, HTML code, or image URL/base64
    title: Optional[str] = None
    # Extra metadata (optional)
    prompt: Optional[str] = None   # the original prompt that produced this


class ShareResponse(BaseModel):
    id: str
    url: str
    created_at: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@share_router.post("", response_model=ShareResponse)
async def create_share(body: CreateShareBody, authorization: str = Header(None)):
    """Create a new public share link (authenticated users only)."""
    payload = _decode_bearer(authorization)
    if not payload:
        raise HTTPException(401, "Authentication required")

    uid = payload["sub"]
    db = await _get_db()
    if db is None:
        raise HTTPException(503, "Database unavailable")

    # Validate content type
    allowed_types = {"text", "app", "image"}
    if body.content_type not in allowed_types:
        raise HTTPException(400, f"content_type must be one of: {', '.join(allowed_types)}")

    # Content size guard — 2MB max (base64 image or large HTML)
    if len(body.content.encode("utf-8")) > 2 * 1024 * 1024:
        raise HTTPException(413, "Content too large — max 2 MB")

    # Fetch author name
    user = await db["users"].find_one({"id": uid}, {"name": 1})
    author_name = user.get("name", "Anonymous") if user else "Anonymous"

    share_id = uuid.uuid4().hex[:12]   # 12-char hex → 4B+ combinations
    now = time.time()

    doc = {
        "id":           share_id,
        "user_id":      uid,
        "author_name":  author_name,
        "content_type": body.content_type,
        "content":      body.content,
        "title":        (body.title or "").strip() or None,
        "prompt":       (body.prompt or "").strip() or None,
        "created_at":   now,
        "views":        0,
    }

    await db["shares"].insert_one(doc)
    log.info("share.create: user=%s type=%s id=%s", uid, body.content_type, share_id)

    return ShareResponse(
        id=share_id,
        url=f"{FRONTEND_URL}/s/{share_id}",
        created_at=now,
    )


@share_router.get("/{share_id}")
async def get_share(share_id: str):
    """Fetch a shared item — public, no auth required."""
    db = await _get_db()
    if db is None:
        raise HTTPException(503, "Database unavailable")

    # Increment view count atomically
    doc = await db["shares"].find_one_and_update(
        {"id": share_id},
        {"$inc": {"views": 1}},
        return_document=True,
    )
    if not doc:
        raise HTTPException(404, "Share not found or has been deleted")

    return {
        "id":           doc["id"],
        "content_type": doc["content_type"],
        "content":      doc["content"],
        "title":        doc.get("title"),
        "prompt":       doc.get("prompt"),
        "author_name":  doc.get("author_name", "Anonymous"),
        "created_at":   doc["created_at"],
        "views":        doc.get("views", 0),
    }


@share_router.delete("/{share_id}")
async def delete_share(share_id: str, authorization: str = Header(None)):
    """Delete own share (or admin can delete any)."""
    payload = _decode_bearer(authorization)
    if not payload:
        raise HTTPException(401, "Authentication required")

    uid = payload["sub"]
    db = await _get_db()
    if db is None:
        raise HTTPException(503, "Database unavailable")

    doc = await db["shares"].find_one({"id": share_id})
    if not doc:
        raise HTTPException(404, "Share not found")

    # Only owner or admin can delete
    user = await db["users"].find_one({"id": uid}, {"role": 1})
    is_admin = user and user.get("role") == "admin"
    if doc["user_id"] != uid and not is_admin:
        raise HTTPException(403, "Forbidden")

    await db["shares"].delete_one({"id": share_id})
    log.info("share.delete: user=%s id=%s", uid, share_id)
    return {"ok": True}
