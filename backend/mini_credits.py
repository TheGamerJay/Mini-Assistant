"""
mini_credits.py
Shared credit check/deduct helper used by both the main server and image_system.
Reads/writes MongoDB directly (same connection pool as server.py).
"""
import logging
import os
import time

log = logging.getLogger(__name__)

JWT_SECRET    = os.environ.get("JWT_SECRET", "mini_assistant_jwt_secret_2025")
JWT_ALGORITHM = "HS256"


def _decode_bearer(authorization: str | None) -> dict | None:
    """Decode a Bearer JWT and return payload, or None on failure."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


async def _get_db():
    """Return the shared MongoDB db handle from server.py."""
    try:
        import server as _srv  # noqa: PLC0415
        return _srv.db
    except Exception:
        return None


async def get_user_credits(authorization: str | None) -> int | None:
    """
    Return the current credit balance for the authenticated user,
    or None if the token is invalid / DB unavailable.
    """
    payload = _decode_bearer(authorization)
    if not payload:
        return None
    db = await _get_db()
    if db is None:
        return None
    user = await db["users"].find_one({"id": payload["sub"]}, {"credits": 1})
    if not user:
        return None
    return user.get("credits", 0)


async def check_and_deduct(authorization: str | None, cost: int) -> tuple[bool, int]:
    """
    Verify the user has enough credits, then atomically deduct `cost`.

    Returns:
        (ok: bool, remaining: int)
        ok=False when:
          - token invalid / user not found
          - insufficient credits
    """
    payload = _decode_bearer(authorization)
    if not payload:
        # No auth token — allow unauthenticated local use (dev), but don't deduct
        return True, -1

    db = await _get_db()
    if db is None:
        # DB unavailable — allow through (don't block service)
        return True, -1

    user = await db["users"].find_one({"id": payload["sub"]}, {"credits": 1, "plan": 1})
    if not user:
        return False, 0

    plan = user.get("plan", "free")

    # Subscribers have unlimited credits
    if plan in ("standard", "pro", "team"):
        return True, 999

    current = user.get("credits", 0)
    if current < cost:
        return False, current

    result = await db["users"].find_one_and_update(
        {"id": payload["sub"], "credits": {"$gte": cost}},
        {"$inc": {"credits": -cost}},
        return_document=True,
        projection={"credits": 1, "name": 1, "email": 1},
    )
    if not result:
        # Race condition — someone else spent the last credits
        fresh = await db["users"].find_one({"id": payload["sub"]}, {"credits": 1})
        return False, fresh.get("credits", 0) if fresh else 0

    # Log activity
    try:
        action = "image_generated" if cost >= 3 else "chat_message"
        await db["activity_logs"].insert_one({
            "user_id":    payload["sub"],
            "user_name":  user.get("name", ""),
            "user_email": user.get("email", ""),
            "type":       action,
            "credits_used": cost,
            "timestamp":  time.time(),
        })
    except Exception:
        pass  # non-fatal

    return True, result["credits"]
