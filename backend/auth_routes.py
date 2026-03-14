"""
auth_routes.py
JWT-based authentication + MongoDB-backed chat/project/image sync for Mini Assistant.
Mounted in server.py via:
    app.include_router(auth_router)
    app.include_router(db_router)
"""

import os
import uuid
import time
import logging

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List, Any

from jose import jwt, JWTError
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Shared db handle — imported from server.py at module level.
# We do a lazy import inside each route to avoid circular-import issues at
# startup; server.py sets `db` before any request is handled.
# ---------------------------------------------------------------------------
def _get_db():
    import server as _srv  # noqa: PLC0415
    if _srv.db is None:
        raise HTTPException(status_code=503, detail="Database not configured (MONGO_URL env var not set)")
    return _srv.db


# ---------------------------------------------------------------------------
# JWT / password config
# ---------------------------------------------------------------------------
JWT_SECRET = os.environ.get("JWT_SECRET", "mini_assistant_jwt_secret_2025")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def _make_token(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user.get("role", "user"),
        "exp": int(time.time()) + JWT_EXPIRY_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}")


async def get_current_user(authorization: str = Header(None)) -> dict:
    """Dependency: decode Bearer token and return the user document from DB."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1]
    payload = _decode_token(token)
    db = _get_db()
    user = await db["users"].find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "avatar": user.get("avatar"),
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterBody(BaseModel):
    name: str
    email: str
    password: str
    security_question: Optional[str] = None
    security_answer: Optional[str] = None


class LoginBody(BaseModel):
    email: str
    password: str


class UpdateProfileBody(BaseModel):
    name: str


class UpdateAvatarBody(BaseModel):
    avatar: Optional[str] = None  # base64 data URL or null to remove


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordBody(BaseModel):
    email: str
    answer: str
    new_password: str


class ChatsBody(BaseModel):
    chats: List[Any] = []


class ProjectsBody(BaseModel):
    projects: List[Any] = []


class ImagesBody(BaseModel):
    images: List[Any] = []


# ---------------------------------------------------------------------------
# Auth router  (/api/auth/*)
# ---------------------------------------------------------------------------
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/register")
async def register(body: RegisterBody):
    db = _get_db()
    email_lc = body.email.strip().lower()

    # Check duplicate
    if await db["users"].find_one({"email": email_lc}):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # First user → admin
    count = await db["users"].count_documents({})
    role = "admin" if count == 0 else "user"

    # Hash security answer
    sec_answer_hash = None
    if body.security_question and body.security_answer:
        sec_answer_hash = _hash_password(body.security_answer.strip().lower())

    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email_lc,
        "name": body.name.strip(),
        "password_hash": _hash_password(body.password),
        "role": role,
        "security_question": body.security_question or None,
        "security_answer_hash": sec_answer_hash,
        "avatar": None,
        "created_at": time.time(),
    }
    await db["users"].insert_one(user_doc)
    token = _make_token(user_doc)
    return {"token": token, "user": _public_user(user_doc)}


@auth_router.post("/login")
async def login(body: LoginBody):
    db = _get_db()
    email_lc = body.email.strip().lower()
    user = await db["users"].find_one({"email": email_lc})
    if not user:
        raise HTTPException(status_code=401, detail="No account found with this email.")
    if not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    token = _make_token(user)
    return {"token": token, "user": _public_user(user)}


@auth_router.get("/me")
async def me(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    return _public_user(user)


@auth_router.patch("/profile")
async def update_profile(body: UpdateProfileBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    await db["users"].update_one({"id": user["id"]}, {"$set": {"name": name}})
    return {"ok": True, "name": name}


@auth_router.patch("/avatar")
async def update_avatar(body: UpdateAvatarBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    await db["users"].update_one({"id": user["id"]}, {"$set": {"avatar": body.avatar}})
    return {"ok": True}


@auth_router.post("/change-password")
async def change_password(body: ChangePasswordBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    if not _verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    new_hash = _hash_password(body.new_password)
    await db["users"].update_one({"id": user["id"]}, {"$set": {"password_hash": new_hash}})
    return {"ok": True}


@auth_router.delete("/account")
async def delete_account(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    uid = user["id"]
    await db["users"].delete_one({"id": uid})
    await db["chats"].delete_many({"user_id": uid})
    await db["projects"].delete_many({"user_id": uid})
    await db["images"].delete_many({"user_id": uid})
    return {"ok": True}


@auth_router.get("/security-question")
async def security_question(email: str):
    db = _get_db()
    user = await db["users"].find_one({"email": email.strip().lower()})
    if not user or not user.get("security_question"):
        raise HTTPException(status_code=404, detail="No account or security question found for this email.")
    return {"security_question": user["security_question"]}


@auth_router.post("/reset-password")
async def reset_password(body: ResetPasswordBody):
    db = _get_db()
    email_lc = body.email.strip().lower()
    user = await db["users"].find_one({"email": email_lc})
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email.")
    if not user.get("security_answer_hash"):
        raise HTTPException(status_code=400, detail="No security question set for this account.")
    if not _verify_password(body.answer.strip().lower(), user["security_answer_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect answer. Please try again.")
    new_hash = _hash_password(body.new_password)
    await db["users"].update_one({"id": user["id"]}, {"$set": {"password_hash": new_hash}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# DB sync router  (/api/db/*)
# ---------------------------------------------------------------------------
db_router = APIRouter(prefix="/api/db", tags=["db-sync"])


@db_router.get("/chats")
async def get_chats(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    doc = await db["chats"].find_one({"user_id": user["id"]})
    return {"chats": doc["chats"] if doc else []}


@db_router.post("/chats")
async def save_chats(body: ChatsBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    await db["chats"].replace_one(
        {"user_id": user["id"]},
        {"user_id": user["id"], "chats": body.chats, "updated_at": time.time()},
        upsert=True,
    )
    return {"ok": True}


@db_router.get("/projects")
async def get_projects(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    doc = await db["projects"].find_one({"user_id": user["id"]})
    return {"projects": doc["projects"] if doc else []}


@db_router.post("/projects")
async def save_projects(body: ProjectsBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    await db["projects"].replace_one(
        {"user_id": user["id"]},
        {"user_id": user["id"], "projects": body.projects, "updated_at": time.time()},
        upsert=True,
    )
    return {"ok": True}


@db_router.get("/images")
async def get_images(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    doc = await db["images"].find_one({"user_id": user["id"]})
    # Return images but strip any full base64 — only thumbnails go over the wire
    images = []
    for img in (doc["images"] if doc else []):
        images.append({k: v for k, v in img.items() if k != "full_base64"})
    return {"images": images}


@db_router.post("/images")
async def save_images(body: ImagesBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    await db["images"].replace_one(
        {"user_id": user["id"]},
        {"user_id": user["id"], "images": body.images, "updated_at": time.time()},
        upsert=True,
    )
    return {"ok": True}
