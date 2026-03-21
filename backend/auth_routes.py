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

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List, Any

try:
    from jose import jwt, JWTError
    from passlib.context import CryptContext
    _AUTH_AVAILABLE = True
except ImportError as _auth_import_err:
    logging.warning("JWT/passlib not available (%s) — auth endpoints disabled, db-sync still works", _auth_import_err)
    jwt = JWTError = CryptContext = None  # type: ignore
    _AUTH_AVAILABLE = False

try:
    from google.oauth2 import id_token as google_id_token
    import google.auth.transport.requests as google_requests
    _GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    google_id_token = google_requests = None  # type: ignore
    _GOOGLE_AUTH_AVAILABLE = False

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

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

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto") if _AUTH_AVAILABLE else None

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(plain: str) -> str:
    if not _AUTH_AVAILABLE: raise HTTPException(status_code=503, detail="Auth not available")
    return pwd_ctx.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    if not _AUTH_AVAILABLE: raise HTTPException(status_code=503, detail="Auth not available")
    return pwd_ctx.verify(plain, hashed)


def _make_token(user: dict) -> str:
    if not _AUTH_AVAILABLE: raise HTTPException(status_code=503, detail="Auth not available")
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user.get("role", "user"),
        "exp": int(time.time()) + JWT_EXPIRY_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    if not _AUTH_AVAILABLE: raise HTTPException(status_code=503, detail="Auth not available")
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
        "credits": user.get("credits", 0),
        "plan": user.get("plan", "free"),
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


class GoogleAuthBody(BaseModel):
    credential: str  # Google ID token from frontend


class ChatsBody(BaseModel):
    chats: List[Any] = []


class ProjectsBody(BaseModel):
    projects: List[Any] = []


class ImagesBody(BaseModel):
    images: List[Any] = []


class SettingsBody(BaseModel):
    settings: dict = {}


class TemplatesBody(BaseModel):
    templates: List[Any] = []


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
        "credits": 10,
        "plan": "free",
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


@auth_router.post("/google")
async def google_login(body: GoogleAuthBody):
    """Sign in / sign up via Google OAuth.
    Accepts either a Google ID token (credential) or an access token.
    Verifies it with Google, then finds or creates a user in MongoDB."""
    import httpx

    token = body.credential.strip()
    idinfo: dict = {}

    # Try ID token verification first (works when GOOGLE_CLIENT_ID is set)
    if _GOOGLE_AUTH_AVAILABLE and GOOGLE_CLIENT_ID:
        try:
            req = google_requests.Request()
            idinfo = google_id_token.verify_oauth2_token(token, req, GOOGLE_CLIENT_ID)
        except Exception:
            idinfo = {}

    # Fallback: validate as access token via Google tokeninfo endpoint
    if not idinfo.get("email"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"https://www.googleapis.com/oauth2/v3/userinfo",
                                     headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    idinfo = r.json()
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Could not verify Google token: {exc}")

    if not idinfo.get("email"):
        raise HTTPException(status_code=401, detail="Google token verification failed")

    google_email = idinfo.get("email", "").strip().lower()
    google_name  = idinfo.get("name", "").strip() or google_email.split("@")[0]
    google_sub   = idinfo.get("sub", "")
    google_pic   = idinfo.get("picture")

    if not google_email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    db = _get_db()

    # Try to find existing user by google_sub first, then by email
    user = await db["users"].find_one({"google_sub": google_sub})
    if not user:
        user = await db["users"].find_one({"email": google_email})

    if user:
        # Existing user — link google_sub if not already set
        updates: dict = {}
        if not user.get("google_sub"):
            updates["google_sub"] = google_sub
        if google_pic and not user.get("avatar"):
            updates["avatar"] = google_pic
        if updates:
            await db["users"].update_one({"id": user["id"]}, {"$set": updates})
            user.update(updates)
    else:
        # New user — create account (no password required)
        count = await db["users"].count_documents({})
        role = "admin" if count == 0 else "user"
        user = {
            "id": str(uuid.uuid4()),
            "email": google_email,
            "name": google_name,
            "password_hash": None,
            "google_sub": google_sub,
            "role": role,
            "avatar": google_pic,
            "credits": 10,
            "plan": "free",
            "created_at": time.time(),
        }
        await db["users"].insert_one(user)

    token = _make_token(user)
    return {"token": token, "user": _public_user(user)}


@auth_router.get("/me")
async def me(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    return _public_user(user)


@auth_router.get("/credits")
async def get_credits(authorization: str = Header(None)):
    """Return current credit balance and plan for the authenticated user."""
    user = await get_current_user(authorization)
    return {"credits": user.get("credits", 0), "plan": user.get("plan", "free")}


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
    await db["settings"].delete_many({"user_id": uid})
    await db["templates"].delete_many({"user_id": uid})
    await db["tasks"].delete_many({"user_id": uid})
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


@db_router.get("/settings")
async def get_settings(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    doc = await db["settings"].find_one({"user_id": user["id"]})
    return {"settings": doc["settings"] if doc else {}}


@db_router.post("/settings")
async def save_settings(body: SettingsBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    await db["settings"].replace_one(
        {"user_id": user["id"]},
        {"user_id": user["id"], "settings": body.settings, "updated_at": time.time()},
        upsert=True,
    )
    return {"ok": True}


@db_router.get("/templates")
async def get_templates(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    doc = await db["templates"].find_one({"user_id": user["id"]})
    return {"templates": doc["templates"] if doc else []}


@db_router.post("/templates")
async def save_templates(body: TemplatesBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    await db["templates"].replace_one(
        {"user_id": user["id"]},
        {"user_id": user["id"], "templates": body.templates, "updated_at": time.time()},
        upsert=True,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tasks router  (/api/tasks/*)
# ---------------------------------------------------------------------------

tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskBody(BaseModel):
    text: str


class TaskUpdateBody(BaseModel):
    text: Optional[str] = None
    done: Optional[bool] = None


@tasks_router.get("")
async def get_tasks(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    doc = await db["tasks"].find_one({"user_id": user["id"]})
    return {"tasks": doc.get("tasks", []) if doc else []}


@tasks_router.post("")
async def add_task(body: TaskBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    task = {
        "id": str(uuid.uuid4()),
        "text": body.text.strip(),
        "done": False,
        "created_at": time.time(),
    }
    await db["tasks"].update_one(
        {"user_id": user["id"]},
        {"$push": {"tasks": task}},
        upsert=True,
    )
    return {"task": task}


@tasks_router.patch("/{task_id}")
async def update_task(task_id: str, body: TaskUpdateBody, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    doc = await db["tasks"].find_one({"user_id": user["id"]})
    tasks = doc.get("tasks", []) if doc else []
    for t in tasks:
        if t["id"] == task_id:
            if body.text is not None:
                t["text"] = body.text.strip()
            if body.done is not None:
                t["done"] = body.done
            break
    await db["tasks"].update_one({"user_id": user["id"]}, {"$set": {"tasks": tasks}})
    return {"ok": True}


@tasks_router.delete("/{task_id}")
async def delete_task(task_id: str, authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    await db["tasks"].update_one(
        {"user_id": user["id"]},
        {"$pull": {"tasks": {"id": task_id}}},
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin router  (/api/admin/*)
# ---------------------------------------------------------------------------
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _require_admin(authorization: str = Header(None)) -> dict:
    """Dependency: decode token and assert admin role."""
    user = await get_current_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


class SetRoleBody(BaseModel):
    role: str  # "admin" | "user"


@admin_router.get("/users")
async def admin_list_users(admin: dict = Depends(_require_admin)):
    """Return all registered users (without password hashes)."""
    db = _get_db()
    users = await db["users"].find({}).to_list(5000)
    return {
        "users": [
            {
                "id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "role": u.get("role", "user"),
                "avatar": u.get("avatar"),
                "created_at": u.get("created_at"),
            }
            for u in users
        ]
    }


@admin_router.get("/stats")
async def admin_stats(admin: dict = Depends(_require_admin)):
    """Aggregate platform-wide stats from MongoDB."""
    db = _get_db()
    total_users = await db["users"].count_documents({})
    total_admins = await db["users"].count_documents({"role": "admin"})

    total_chats = 0
    total_messages = 0
    thumbs_up = 0
    thumbs_down = 0

    async for doc in db["chats"].find({}):
        chats = doc.get("chats", [])
        total_chats += len(chats)
        for chat in chats:
            msgs = chat.get("messages", [])
            total_messages += len(msgs)
            for m in msgs:
                if m.get("rating") == 1:
                    thumbs_up += 1
                elif m.get("rating") == -1:
                    thumbs_down += 1

    total_image_docs = await db["images"].count_documents({})

    return {
        "total_users": total_users,
        "total_admins": total_admins,
        "total_chats": total_chats,
        "total_messages": total_messages,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "total_image_docs": total_image_docs,
        "server_time": time.time(),
    }


@admin_router.patch("/users/{user_id}/role")
async def admin_set_role(user_id: str, body: SetRoleBody, admin: dict = Depends(_require_admin)):
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'.")
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")
    db = _get_db()
    result = await db["users"].update_one({"id": user_id}, {"$set": {"role": body.role}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True}


@admin_router.delete("/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(_require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account here.")
    db = _get_db()
    result = await db["users"].delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    # Cascade-delete all user data
    await db["chats"].delete_many({"user_id": user_id})
    await db["projects"].delete_many({"user_id": user_id})
    await db["images"].delete_many({"user_id": user_id})
    await db["settings"].delete_many({"user_id": user_id})
    await db["templates"].delete_many({"user_id": user_id})
    await db["tasks"].delete_many({"user_id": user_id})
    return {"ok": True}
