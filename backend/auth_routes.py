"""
auth_routes.py
JWT-based authentication + MongoDB-backed chat/project/image sync for Mini Assistant.
Mounted in server.py via:
    app.include_router(auth_router)
    app.include_router(db_router)
"""

import asyncio
import collections
import os
import secrets
import string
import uuid
import time
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Header, Request
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
        "has_ad_mode": user.get("has_ad_mode", False),
        "referral_code": user.get("referral_code"),
        "referrals_rewarded_count": user.get("referrals_rewarded_count", 0),
        # True for existing users (backward compat) and Google OAuth users
        "email_verified": user.get("email_verified", True),
    }


# Referral constants
REFERRAL_SIGNUP_BONUS   = 5    # credits given to new user on signup with referral
REFERRAL_SUB_BONUS      = 50   # credits given to both parties on subscription
REFERRAL_MAX_REWARDS    = 3    # default max (free/standard plans)

# Plan-based referral caps — must match stripe_handler.py
REFERRAL_MAX_REWARDS_BY_PLAN: dict[str, int] = {
    "free":     3,
    "standard": 3,
    "pro":      6,
    "max":      10,
    "team":     10,
}

# ---------------------------------------------------------------------------
# Anti-abuse constants
# ---------------------------------------------------------------------------

SIGNUP_CREDITS      = 5     # credits granted AFTER email verification (down from 10)
VERIFY_TOKEN_EXPIRY = 86400 # 24 hours in seconds
FREE_CREDIT_TTL     = 7 * 86400  # free credits expire after 7 days

# In-memory IP-based signup rate limiter  {ip: [timestamps]}
_signup_attempts: dict = collections.defaultdict(list)
SIGNUP_RATE_LIMIT  = 3     # max signups per IP per window
SIGNUP_RATE_WINDOW = 3600  # 1 hour

# Disposable / throwaway email domains
DISPOSABLE_EMAIL_DOMAINS: frozenset = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.info", "guerrillamail.biz",
    "guerrillamail.de", "guerrillamail.net", "guerrillamail.org", "guerrillamailblock.com",
    "sharklasers.com", "grr.la", "spam4.me", "trashmail.com", "trashmail.me",
    "trashmail.net", "trashmail.io", "trashmail.at", "trashdevil.com", "trashdevil.de",
    "trashmailer.com", "dispostable.com", "yopmail.com", "yopmail.fr", "cool.fr.nf",
    "jetable.fr.nf", "jetable.com", "jetable.net", "jetable.org", "nospam.ze.tc",
    "nomail.xl.cx", "10minutemail.com", "10minutemail.net", "10minutemail.org",
    "10minemail.com", "minutemailbox.com", "mailnull.com", "spamgourmet.com",
    "spamgourmet.net", "spamgourmet.org", "spamgourmet.me", "mailnesia.com",
    "tempr.email", "discard.email", "discardmail.com", "discardmail.de",
    "cuvox.de", "dayrep.com", "einrot.com", "fleckens.hu", "gustr.com",
    "jourrapide.com", "rhyta.com", "superrito.com", "teleworm.us", "armyspy.com",
    "maildrop.cc", "spamfree24.org", "fakemail.net", "fakeinbox.com", "fakeinbox.net",
    "fakemail.fr", "filzmail.com", "filzmail.de", "mailfreeonline.com",
    "getnada.com", "nada.email", "nadaemail.com", "mohmal.com", "moakt.com", "moakt.ws",
    "mailcatch.com", "mailexpire.com", "mailme.ir", "spamgob.com", "spamgob.net",
    "binkmail.com", "bobmail.info", "chammy.info", "devnullmail.com", "dodgit.com",
    "dumpandforfeit.com", "dumpmail.de", "email60.com", "emailfake.com", "emailigo.com",
    "gishpuppy.com", "haltospam.com", "hatespam.org", "ieatspam.eu", "ieatspam.info",
    "kasmail.com", "klzlk.com", "kurzepost.de", "maileater.com", "mailipsum.com",
    "meltmail.com", "noclickemail.com", "nospamfor.us", "objectmail.com", "odaymail.com",
    "oneoffemail.com", "pookmail.com", "rppkn.com", "safe-mail.net", "sharedmailbox.org",
    "shortmail.net", "spamavert.com", "spambe.com", "spamgone.com", "spamhereatme.com",
    "spaminmotion.com", "spamme.dk", "spamoff.de", "spamspot.com", "spamthis.co.uk",
    "spamthisplease.com", "temporaryemail.com", "temporaryforwarding.com",
    "temporaryinbox.com", "tempymail.com", "throwam.com", "throwam.net",
    "throwam.org", "throwam.me", "tyldd.com", "uggsrock.com", "wegwerfmail.de",
    "wegwerfmail.net", "wegwerfmail.org", "xagloo.com", "yepmail.net", "yobshmail.com",
    "zippymail.info", "getairmail.com", "tempinbox.com", "crazymailing.com",
    "mailsucker.net", "spamherelots.com",
})


def _check_disposable_email(email: str) -> None:
    """Raise 400 if the email domain is a known disposable email service."""
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail="Disposable email addresses are not allowed. Please use a real email address.",
        )


def _check_signup_rate_limit(ip: str) -> None:
    """Raise 429 if IP has exceeded signup rate limit."""
    if ip in ("127.0.0.1", "::1", "unknown"):
        return  # never rate-limit localhost (dev)
    now = time.time()
    _signup_attempts[ip] = [t for t in _signup_attempts[ip] if now - t < SIGNUP_RATE_WINDOW]
    if len(_signup_attempts[ip]) >= SIGNUP_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many signup attempts from this IP. Please try again in 1 hour.",
        )
    _signup_attempts[ip].append(now)


def _gen_verify_token() -> str:
    """Generate a 48-char hex email verification token."""
    return secrets.token_hex(24)


def _expire_free_credits_if_needed(user: dict) -> int:
    """Return the effective credit balance, zeroing out expired free credits."""
    if user.get("plan", "free") != "free":
        return user.get("credits", 0)
    expire_at = user.get("free_credits_expire_at")
    if expire_at and expire_at < time.time() and user.get("credits", 0) > 0:
        return -1  # signal: should zero out in DB
    return user.get("credits", 0)


def _gen_referral_code() -> str:
    """Generate a unique 8-char alphanumeric referral code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterBody(BaseModel):
    name: str
    email: str
    password: str
    security_question: Optional[str] = None
    security_answer: Optional[str] = None
    referral_code: Optional[str] = None  # referral code of the person who invited them


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


class VerifyEmailBody(BaseModel):
    token: str


class ResendVerifyBody(BaseModel):
    pass  # auth header carries the identity


# ---------------------------------------------------------------------------
# Auth router  (/api/auth/*)
# ---------------------------------------------------------------------------
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/register")
async def register(body: RegisterBody, request: Request):
    db = _get_db()
    email_lc = body.email.strip().lower()
    client_ip = (request.client.host if request.client else None) or "unknown"

    # ── Phase 6: IP signup rate limit ──────────────────────────────────────
    _check_signup_rate_limit(client_ip)

    # ── Phase 3: Block disposable emails ───────────────────────────────────
    _check_disposable_email(email_lc)

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

    # ── Phase 5: Validate referral code + IP self-referral check ───────────
    referrer = None
    referred_by_code = (body.referral_code or "").strip().upper() or None
    if referred_by_code:
        referrer = await db["users"].find_one({"referral_code": referred_by_code})
        if not referrer:
            referred_by_code = None  # invalid code — ignore silently
        elif referrer.get("signup_ip") and referrer["signup_ip"] == client_ip:
            # Same IP = likely self-referral
            log.info("referral.blocked: same-IP self-referral from %s", client_ip)
            referred_by_code = None
            referrer = None

    # ── Phase 1: Credits start at 0 — granted after email verification ─────
    # ── Phase 2: Signup credits reduced to SIGNUP_CREDITS (5) ─────────────
    pending_credits = SIGNUP_CREDITS + (REFERRAL_SIGNUP_BONUS if referred_by_code else 0)

    # Generate email verification token
    verify_token = _gen_verify_token()

    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email_lc,
        "name": body.name.strip(),
        "password_hash": _hash_password(body.password),
        "role": role,
        "security_question": body.security_question or None,
        "security_answer_hash": sec_answer_hash,
        "avatar": None,
        "credits": 0,                   # Phase 1: no credits until email verified
        "pending_credits": pending_credits,  # granted on verification
        "plan": "free",
        "created_at": time.time(),
        "signup_ip": client_ip,
        "referral_code": _gen_referral_code(),
        "referred_by": referred_by_code,
        "referral_reward_given": False,
        "referrals_rewarded_count": 0,
        # Email verification
        "email_verified": False,
        "email_verify_token": verify_token,
        "email_verify_expires": time.time() + VERIFY_TOKEN_EXPIRY,
        # Phase 4: credit expiry (set when verification completes)
        "free_credits_expire_at": None,
    }
    await db["users"].insert_one(user_doc)

    # Notify referrer about signup (non-blocking)
    if referred_by_code and referrer:
        log.info("referral.signup: new user=%s referred_by=%s", user_doc["id"], referred_by_code)
        async def _notify_referrer():
            try:
                from email_sender import send_referral_signup_email  # noqa: PLC0415
                db2 = _get_db()
                await send_referral_signup_email(
                    to_email=referrer["email"],
                    to_name=referrer.get("name", "there"),
                    sub_bonus=REFERRAL_SUB_BONUS,
                    user_id=referrer["id"],
                    db=db2,
                )
            except Exception as _e:
                log.warning("referral signup email failed (non-fatal): %s", _e)
        asyncio.create_task(_notify_referrer())

    # Send verification email (non-blocking)
    async def _send_verify():
        try:
            from email_service import send_verification_email  # noqa: PLC0415
            await send_verification_email(email_lc, body.name.strip(), verify_token)
        except Exception as _e:
            log.warning("Verification email failed (non-fatal): %s", _e)
    asyncio.create_task(_send_verify())

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


@auth_router.post("/verify-email")
async def verify_email(body: VerifyEmailBody):
    """Verify email using the token from the verification link. Grants signup credits."""
    db = _get_db()
    user = await db["users"].find_one({"email_verify_token": body.token})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link.")
    if user.get("email_verified"):
        # Already verified — just return a fresh token
        token = _make_token(user)
        return {"token": token, "user": _public_user(user), "message": "Email already verified."}
    if user.get("email_verify_expires", 0) < time.time():
        raise HTTPException(
            status_code=400,
            detail="Verification link has expired. Please request a new one.",
        )

    pending = user.get("pending_credits", SIGNUP_CREDITS)
    now = time.time()
    await db["users"].update_one(
        {"id": user["id"]},
        {"$set": {
            "email_verified": True,
            "credits": pending,
            "pending_credits": 0,
            "email_verify_token": None,
            "email_verify_expires": None,
            "free_credits_expire_at": now + FREE_CREDIT_TTL,  # Phase 4: 7-day expiry
        }},
    )
    user["email_verified"] = True
    user["credits"] = pending

    # Send welcome email now that verification is confirmed
    try:
        from email_service import send_welcome_email  # noqa: PLC0415
        threading.Thread(
            target=send_welcome_email,
            args=(user["email"], user["name"], user["id"]),
            daemon=True,
        ).start()
    except Exception as _e:
        log.warning("Welcome email failed (non-fatal): %s", _e)

    token = _make_token(user)
    return {"token": token, "user": _public_user(user), "message": "Email verified! Credits granted."}


@auth_router.post("/resend-verification")
async def resend_verification(authorization: str = Header(None)):
    """Resend the email verification link to the authenticated user."""
    user = await get_current_user(authorization)
    if user.get("email_verified", True):
        return {"message": "Email already verified."}
    db = _get_db()
    verify_token = _gen_verify_token()
    await db["users"].update_one(
        {"id": user["id"]},
        {"$set": {
            "email_verify_token": verify_token,
            "email_verify_expires": time.time() + VERIFY_TOKEN_EXPIRY,
        }},
    )
    async def _send():
        try:
            from email_service import send_verification_email  # noqa: PLC0415
            await send_verification_email(user["email"], user.get("name", ""), verify_token)
        except Exception as _e:
            log.warning("Resend verification failed (non-fatal): %s", _e)
    asyncio.create_task(_send())
    return {"message": "Verification email sent."}


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
        now = time.time()
        user = {
            "id": str(uuid.uuid4()),
            "email": google_email,
            "name": google_name,
            "password_hash": None,
            "google_sub": google_sub,
            "role": role,
            "avatar": google_pic,
            "credits": SIGNUP_CREDITS,   # Phase 2: reduced signup credits
            "pending_credits": 0,
            "plan": "free",
            "created_at": now,
            "signup_ip": None,
            "referral_code": _gen_referral_code(),
            "referred_by": None,
            "referral_reward_given": False,
            "referrals_rewarded_count": 0,
            "email_verified": True,      # Google already verified the email
            "email_verify_token": None,
            "email_verify_expires": None,
            "free_credits_expire_at": now + FREE_CREDIT_TTL,  # Phase 4: 7-day expiry
        }
        await db["users"].insert_one(user)

        # Fire welcome email for new Google sign-ups
        try:
            from email_service import send_welcome_email  # noqa: PLC0415
            threading.Thread(
                target=send_welcome_email,
                args=(user["email"], user["name"], user["id"]),
                daemon=True,
            ).start()
        except Exception as _email_exc:
            log.warning("Could not start welcome email thread: %s", _email_exc)

    token = _make_token(user)
    return {"token": token, "user": _public_user(user)}


@auth_router.get("/me")
async def me(authorization: str = Header(None)):
    user = await get_current_user(authorization)
    db = _get_db()
    updates: dict = {}
    # Backfill starter credits for pre-existing accounts
    if "credits" not in user:
        updates["credits"] = 10
        updates["plan"] = "free"
    # Phase 4: zero out expired free credits
    effective = _expire_free_credits_if_needed(user)
    if effective == -1:
        updates["credits"] = 0
        user["credits"] = 0
    if updates:
        await db["users"].update_one({"id": user["id"]}, {"$set": updates})
        user.update(updates)
    return _public_user(user)


@auth_router.get("/credits")
async def get_credits(authorization: str = Header(None)):
    """Return current credit balance and plan for the authenticated user."""
    user = await get_current_user(authorization)
    db = _get_db()
    updates: dict = {}
    # Backfill: existing users have no 'credits' field
    if "credits" not in user:
        updates["credits"] = 10
        updates["plan"] = "free"
    # Phase 4: zero out expired free credits
    effective = _expire_free_credits_if_needed(user)
    if effective == -1:
        updates["credits"] = 0
    if updates:
        await db["users"].update_one({"id": user["id"]}, {"$set": updates})
        user.update(updates)

    # Include image usage so the frontend can enforce limits without a separate call
    from mini_credits import check_image_limit as _img_limit  # noqa: PLC0415
    _img_ok, _img_used, _img_limit_val, _img_resets_on = await _img_limit(authorization, db)

    return {
        "credits":          user.get("credits", 0),
        "plan":             user.get("plan", "free"),
        "images_used":      _img_used,
        "images_limit":     _img_limit_val,
        "images_resets_on": _img_resets_on,
    }


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


@auth_router.get("/referral")
async def get_referral_info(authorization: str = Header(None)):
    """Return current user's referral code, link, and stats (completed + pending)."""
    user = await get_current_user(authorization)
    db = _get_db()
    # Backfill referral_code for pre-existing accounts
    if not user.get("referral_code"):
        code = _gen_referral_code()
        await db["users"].update_one({"id": user["id"]}, {"$set": {
            "referral_code": code,
            "referrals_rewarded_count": 0,
            "referral_reward_given": False,
        }})
        user["referral_code"] = code

    code = user["referral_code"]
    completed  = user.get("referrals_rewarded_count", 0)
    user_plan  = user.get("plan", "free")
    max_rewards = REFERRAL_MAX_REWARDS_BY_PLAN.get(user_plan, REFERRAL_MAX_REWARDS)

    # Count signups using this code that haven't subscribed yet (pending)
    pending = await db["users"].count_documents({
        "referred_by": code,
        "referral_reward_given": {"$ne": True},
    })

    return {
        "referral_code": code,
        "referrals_rewarded_count": completed,
        "referrals_pending_count": pending,
        "max_rewards": max_rewards,
        "slots_remaining": max(0, max_rewards - completed),
        "signup_bonus": REFERRAL_SIGNUP_BONUS,
        "sub_bonus": REFERRAL_SUB_BONUS,
        "plan": user_plan,
        "can_unlock_more": user_plan not in ("max", "team") and completed >= max_rewards,
    }


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
                "credits": u.get("credits", 0),
                "plan": u.get("plan", "free"),
                "bonus_images": u.get("bonus_images", 0),
                "created_at": u.get("created_at"),
                "google_linked": bool(u.get("google_sub")),
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

    # Credits stats — sum credits for all free-plan users (paid plans have unlimited)
    credits_pipeline = [
        {"$match": {"plan": {"$nin": ["standard", "pro", "max", "team"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$credits"}}},
    ]
    credits_result = await db["users"].aggregate(credits_pipeline).to_list(1)
    total_credits_remaining = credits_result[0]["total"] if credits_result else 0

    total_activity = await db["activity_logs"].count_documents({})
    total_images_gen = await db["activity_logs"].count_documents({"type": "image_generated"})
    total_chats_gen = await db["activity_logs"].count_documents({"type": "chat_message"})

    # New users in last 7 days
    week_ago = time.time() - 7 * 86400
    new_users_week = await db["users"].count_documents({"created_at": {"$gte": week_ago}})

    return {
        "total_users": total_users,
        "total_admins": total_admins,
        "new_users_week": new_users_week,
        "total_chats": total_chats,
        "total_messages": total_messages,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "total_image_docs": total_image_docs,
        "total_images_generated": total_images_gen,
        "total_chat_messages": total_chats_gen,
        "total_activity_events": total_activity,
        "total_credits_remaining": total_credits_remaining,
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
    await db["activity_logs"].delete_many({"user_id": user_id})
    return {"ok": True}


class GrantCreditsBody(BaseModel):
    credits: int


@admin_router.patch("/users/{user_id}/credits")
async def admin_grant_credits(user_id: str, body: GrantCreditsBody, admin: dict = Depends(_require_admin)):
    """Set a user's credit balance directly (admin override)."""
    if body.credits < 0:
        raise HTTPException(status_code=400, detail="Credits cannot be negative.")
    db = _get_db()
    result = await db["users"].update_one({"id": user_id}, {"$set": {"credits": body.credits}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "credits": body.credits}


class GrantImagesBody(BaseModel):
    images: int


@admin_router.patch("/users/{user_id}/images")
async def admin_grant_images(user_id: str, body: GrantImagesBody, admin: dict = Depends(_require_admin)):
    """Set a user's bonus image allowance on top of their plan limit (admin override)."""
    if body.images < 0:
        raise HTTPException(status_code=400, detail="Bonus images cannot be negative.")
    db = _get_db()
    result = await db["users"].update_one({"id": user_id}, {"$set": {"bonus_images": body.images}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "bonus_images": body.images}


@auth_router.get("/dashboard")
async def user_dashboard(authorization: str = Header(None)):
    """Return the authenticated user's personal usage stats and recent activity."""
    from datetime import datetime, timezone as _tz
    user = await get_current_user(authorization)
    db = _get_db()

    uid = user["id"]
    plan = user.get("plan", "free")

    # Dual-credit support: subscription_credits + topup_credits
    # Fall back to legacy single `credits` field for old accounts
    sub_credits   = user.get("subscription_credits")
    topup_credits = user.get("topup_credits", 0)

    if sub_credits is not None:
        credits = sub_credits + topup_credits
    else:
        credits = user.get("credits", 0)
        # Auto-backfill missing credits
        if "credits" not in user:
            credits = 10
            await db["users"].update_one({"id": uid}, {"$set": {"credits": 10, "plan": "free"}})

    now = datetime.now(_tz.utc)
    month_key = f"{now.year:04d}-{now.month:02d}"

    # All-time counts
    total_chats_sent  = await db["activity_logs"].count_documents({"user_id": uid, "type": "chat_message"})
    total_images_made = await db["activity_logs"].count_documents({"user_id": uid, "type": "image_generated"})

    # All-time credits used
    agg_all = await db["activity_logs"].aggregate([
        {"$match": {"user_id": uid}},
        {"$group": {"_id": None, "total": {"$sum": "$credits_used"}}},
    ]).to_list(1)
    total_credits_used = agg_all[0].get("total", 0) if agg_all else 0

    # This-month stats
    agg_month = await db["activity_logs"].aggregate([
        {"$match": {"user_id": uid, "month_key": month_key}},
        {"$group": {
            "_id": None,
            "credits": {"$sum": "$credits_used"},
            "requests": {"$sum": 1},
        }},
    ]).to_list(1)
    credits_used_month  = agg_month[0].get("credits", 0) if agg_month else 0
    requests_this_month = agg_month[0].get("requests", 0) if agg_month else 0

    # Most used feature this month
    feat_agg = await db["activity_logs"].aggregate([
        {"$match": {"user_id": uid, "month_key": month_key}},
        {"$group": {"_id": "$action_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1},
    ]).to_list(1)
    most_used_feature = feat_agg[0]["_id"] if feat_agg else None

    # Daily trend — last 7 days (credits + requests per day)
    seven_days_ago = time.time() - 7 * 86400
    daily_agg = await db["activity_logs"].aggregate([
        {"$match": {"user_id": uid, "timestamp": {"$gte": seven_days_ago}}},
        {"$group": {
            "_id": {
                "$dateToString": {
                    "format": "%Y-%m-%d",
                    "date": {"$toDate": {"$multiply": ["$timestamp", 1000]}},
                }
            },
            "credits":  {"$sum": "$credits_used"},
            "requests": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(7)
    daily_trend = [{"date": d["_id"], "credits": d["credits"], "requests": d["requests"]} for d in daily_agg]

    # Recent activity (last 20)
    recent = await db["activity_logs"].find(
        {"user_id": uid}, {"_id": 0}
    ).sort("timestamp", -1).limit(20).to_list(20)

    # Saved chats
    chats_doc = await db["chats"].find_one({"user_id": uid}, {"chats": 1})
    saved_chats = len(chats_doc["chats"]) if chats_doc else 0

    # Saved images
    images_doc = await db["images"].find_one({"user_id": uid}, {"images": 1})
    saved_images = len(images_doc["images"]) if images_doc else 0

    return {
        "plan": plan,
        "credits": credits,
        # Dual-credit breakdown
        "subscription_credits": sub_credits,
        "topup_credits":        topup_credits,
        "billing_cycle_start":  user.get("billing_cycle_start"),
        "stripe_customer_id":   user.get("stripe_customer_id"),
        "is_subscribed": plan in ("standard", "pro", "team"),
        "member_since": user.get("created_at"),
        # All-time
        "total_chats_sent":     total_chats_sent,
        "total_images_made":    total_images_made,
        "total_credits_used":   total_credits_used,
        "saved_chats":          saved_chats,
        "saved_images":         saved_images,
        # This month
        "credits_used_month":   credits_used_month,
        "requests_this_month":  requests_this_month,
        "most_used_feature":    most_used_feature,
        "daily_trend":          daily_trend,
        # Activity
        "recent_activity": recent,
    }


@admin_router.get("/activity")
async def admin_activity(limit: int = 100, admin: dict = Depends(_require_admin)):
    """Return recent activity logs across all users."""
    db = _get_db()
    logs = await db["activity_logs"].find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(min(limit, 500)).to_list(500)
    return {"logs": logs}


@admin_router.get("/abuse-flags")
async def admin_abuse_flags(actioned: bool = False, admin: dict = Depends(_require_admin)):
    """
    Return users flagged for potential abuse.
    actioned=false (default) → only unreviewed flags
    actioned=true            → all flags including actioned ones
    """
    db = _get_db()
    flt = {} if actioned else {"actioned": False}
    flags = await db["abuse_flags"].find(
        flt, {"_id": 0}
    ).sort("last_seen", -1).limit(500).to_list(500)
    return {"flags": flags, "count": len(flags)}


@admin_router.patch("/abuse-flags/{user_id}")
async def admin_action_abuse_flag(user_id: str, body: dict, admin: dict = Depends(_require_admin)):
    """Mark a user's abuse flags as actioned (reviewed)."""
    db = _get_db()
    result = await db["abuse_flags"].update_many(
        {"user_id": user_id},
        {"$set": {
            "actioned":    True,
            "actioned_by": admin.get("email", admin.get("id")),
            "actioned_at": time.time(),
            "action_note": body.get("note", ""),
        }},
    )
    return {"updated": result.modified_count}


@admin_router.get("/system-alerts")
async def admin_system_alerts(limit: int = 50, admin: dict = Depends(_require_admin)):
    """Return recent system-level alerts (margin drops, cost spikes)."""
    db = _get_db()
    alerts = await db["system_alerts"].find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(min(limit, 200)).to_list(200)
    return {"alerts": alerts, "count": len(alerts)}


@admin_router.get("/analytics")
async def admin_analytics(admin: dict = Depends(_require_admin)):
    """
    Unified revenue, cost, and usage analytics for the admin dashboard.

    Returns:
      - users_by_plan        : breakdown of user count per plan
      - mrr_estimate_usd     : estimated monthly recurring revenue
      - ai_cost_this_month   : estimated AI API cost this month (from usage_logs)
      - net_profit_estimate  : MRR minus AI cost estimate
      - profit_margin_pct    : net profit / MRR * 100
      - conversion_rate_pct  : paid users / total users * 100
      - daily_usage          : last 30 days — credits, requests, estimated cost
      - usage_by_action      : per action_type totals
      - paying_users         : count of non-free users
      - new_users_this_month : new registrations this month
    """
    from datetime import datetime, timezone as _tz
    from mini_credits import PLAN_MONTHLY_PRICE_USD

    db = _get_db()
    now = datetime.now(_tz.utc)
    month_key = f"{now.year:04d}-{now.month:02d}"

    # ── Users per plan ──────────────────────────────────────────────────────
    plan_agg = await db["users"].aggregate([
        {"$group": {"_id": "$plan", "count": {"$sum": 1}}},
    ]).to_list(10)
    users_by_plan = {"free": 0, "standard": 0, "pro": 0, "max": 0}
    for row in plan_agg:
        p = row.get("_id") or "free"
        users_by_plan[p] = row.get("count", 0)

    total_users  = sum(users_by_plan.values())
    paying_users = sum(v for k, v in users_by_plan.items() if k != "free")

    # ── Revenue estimate ────────────────────────────────────────────────────
    mrr_estimate = sum(
        count * PLAN_MONTHLY_PRICE_USD.get(plan, 0)
        for plan, count in users_by_plan.items()
    )

    # Revenue per plan
    revenue_by_plan = {
        plan: round(count * PLAN_MONTHLY_PRICE_USD.get(plan, 0), 2)
        for plan, count in users_by_plan.items()
    }

    # ── AI cost this month (from usage_logs) ────────────────────────────────
    cost_agg = await db["activity_logs"].aggregate([
        {"$match": {"month_key": month_key}},
        {"$group": {"_id": None, "cost": {"$sum": "$estimated_cost_usd"}}},
    ]).to_list(1)
    ai_cost_this_month = round(cost_agg[0].get("cost", 0.0), 4) if cost_agg else 0.0

    net_profit = round(mrr_estimate - ai_cost_this_month, 2)
    profit_margin_pct = round((net_profit / mrr_estimate * 100) if mrr_estimate > 0 else 0.0, 1)
    conversion_rate_pct = round((paying_users / total_users * 100) if total_users > 0 else 0.0, 1)

    # ── Daily usage — last 30 days ──────────────────────────────────────────
    thirty_days_ago = time.time() - 30 * 86400
    daily_agg = await db["activity_logs"].aggregate([
        {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": {
                "$dateToString": {
                    "format": "%Y-%m-%d",
                    "date": {"$toDate": {"$multiply": ["$timestamp", 1000]}},
                }
            },
            "credits":  {"$sum": "$credits_used"},
            "requests": {"$sum": 1},
            "cost_usd": {"$sum": "$estimated_cost_usd"},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(30)
    daily_usage = [
        {
            "date":     d["_id"],
            "credits":  d["credits"],
            "requests": d["requests"],
            "cost_usd": round(d.get("cost_usd", 0), 4),
        }
        for d in daily_agg
    ]

    # ── Usage breakdown by action type (all time) ───────────────────────────
    action_agg = await db["activity_logs"].aggregate([
        {"$group": {
            "_id":      "$action_type",
            "credits":  {"$sum": "$credits_used"},
            "requests": {"$sum": 1},
            "cost_usd": {"$sum": "$estimated_cost_usd"},
        }},
        {"$sort": {"requests": -1}},
    ]).to_list(20)
    usage_by_action = [
        {
            "action":   r.get("_id") or "unknown",
            "credits":  r.get("credits", 0),
            "requests": r.get("requests", 0),
            "cost_usd": round(r.get("cost_usd", 0), 4),
        }
        for r in action_agg
    ]

    # ── New users this month ────────────────────────────────────────────────
    month_start_ts = datetime(now.year, now.month, 1, tzinfo=_tz.utc).timestamp()
    new_users_this_month = await db["users"].count_documents(
        {"created_at": {"$gte": month_start_ts}}
    )

    # ── Cost today ──────────────────────────────────────────────────────────
    today_str = now.strftime("%Y-%m-%d")
    today_start_ts = time.time() - (now.hour * 3600 + now.minute * 60 + now.second)
    cost_today_agg = await db["activity_logs"].aggregate([
        {"$match": {"timestamp": {"$gte": today_start_ts}}},
        {"$group": {"_id": None, "cost": {"$sum": "$estimated_cost_usd"}}},
    ]).to_list(1)
    cost_today_usd = round(cost_today_agg[0].get("cost", 0.0), 4) if cost_today_agg else 0.0

    # ── Cost breakdown by plan ───────────────────────────────────────────────
    cost_by_plan_agg = await db["activity_logs"].aggregate([
        {"$match": {"month_key": month_key}},
        {"$group": {
            "_id":      "$plan",
            "cost_usd": {"$sum": "$estimated_cost_usd"},
            "requests": {"$sum": 1},
        }},
    ]).to_list(10)
    cost_by_plan = {
        row.get("_id") or "unknown": {
            "cost_usd": round(row.get("cost_usd", 0), 4),
            "requests": row.get("requests", 0),
        }
        for row in cost_by_plan_agg
    }

    # ── Avg cost per active user this month ─────────────────────────────────
    active_users_this_month_agg = await db["activity_logs"].aggregate([
        {"$match": {"month_key": month_key}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "count"},
    ]).to_list(1)
    active_users_count = active_users_this_month_agg[0]["count"] if active_users_this_month_agg else 0
    avg_cost_per_user_usd = round(ai_cost_this_month / active_users_count, 4) if active_users_count > 0 else 0.0

    # ── Per-plan P&L breakdown ───────────────────────────────────────────────
    all_plans = set(list(users_by_plan.keys()) + list(cost_by_plan.keys()))
    plan_breakdown = []
    for p in sorted(all_plans):
        user_count  = users_by_plan.get(p, 0)
        revenue     = revenue_by_plan.get(p, 0.0)
        cost_data   = cost_by_plan.get(p, {"cost_usd": 0.0, "requests": 0})
        cost        = cost_data["cost_usd"]
        profit      = round(revenue - cost, 4)
        profit_per_user = round(profit / user_count, 4) if user_count > 0 else 0.0
        plan_breakdown.append({
            "plan":            p,
            "users":           user_count,
            "revenue_usd":     revenue,
            "cost_usd":        cost,
            "profit_usd":      profit,
            "profit_per_user": profit_per_user,
            "requests":        cost_data["requests"],
        })

    return {
        "users_by_plan":           users_by_plan,
        "total_users":             total_users,
        "paying_users":            paying_users,
        "new_users_this_month":    new_users_this_month,
        "mrr_estimate_usd":        round(mrr_estimate, 2),
        "ai_cost_this_month_usd":  ai_cost_this_month,
        "cost_today_usd":          cost_today_usd,
        "cost_by_plan":            cost_by_plan,
        "revenue_by_plan":         revenue_by_plan,
        "plan_breakdown":          plan_breakdown,
        "avg_cost_per_user_usd":   avg_cost_per_user_usd,
        "active_users_this_month": active_users_count,
        "net_profit_estimate_usd": net_profit,
        "profit_margin_pct":       profit_margin_pct,
        "conversion_rate_pct":     conversion_rate_pct,
        "daily_usage":             daily_usage,
        "usage_by_action":         usage_by_action,
    }


@admin_router.get("/pricing-optimizer")
async def admin_pricing_optimizer(admin: dict = Depends(_require_admin)):
    """
    Analyze credit pricing vs. actual AI cost to recommend profit-maximizing prices.

    For each action type, calculates:
      - Average AI cost per request
      - Revenue per credit (based on cheapest paid plan)
      - Current margin %
      - Recommended credit cost to achieve target margin
    """
    from mini_credits import CREDIT_COSTS, AI_COST_USD, PLAN_MONTHLY_PRICE_USD, PLAN_CREDIT_LIMITS

    db = _get_db()

    # Revenue per credit = plan_price / plan_credits (cheapest paid plan = standard)
    revenue_per_credit = PLAN_MONTHLY_PRICE_USD["standard"] / PLAN_CREDIT_LIMITS["standard"]  # $0.018/credit
    TARGET_MARGIN = 0.40  # 40% target profit margin

    # Actual avg cost per action from logs (last 30 days)
    thirty_days_ago = time.time() - 30 * 86400
    cost_agg = await db["activity_logs"].aggregate([
        {"$match": {"timestamp": {"$gte": thirty_days_ago}, "action_type": {"$exists": True}}},
        {"$group": {
            "_id":         "$action_type",
            "avg_cost":    {"$avg": "$estimated_cost_usd"},
            "total_cost":  {"$sum": "$estimated_cost_usd"},
            "total_requests": {"$sum": 1},
        }},
    ]).to_list(20)
    actual_costs = {r["_id"]: r for r in cost_agg}

    analysis = []
    for action, credit_cost in CREDIT_COSTS.items():
        avg_cost = (
            actual_costs[action]["avg_cost"]
            if action in actual_costs
            else AI_COST_USD.get(action, 0.005)
        )
        revenue = credit_cost * revenue_per_credit
        margin = ((revenue - avg_cost) / revenue * 100) if revenue > 0 else 0
        # Credits needed to achieve TARGET_MARGIN at current avg cost
        recommended_credits = (avg_cost / (revenue_per_credit * (1 - TARGET_MARGIN))) if revenue_per_credit > 0 else credit_cost
        analysis.append({
            "action":              action,
            "credit_cost":         credit_cost,
            "avg_ai_cost_usd":     round(avg_cost, 5),
            "revenue_estimate_usd": round(revenue, 5),
            "current_margin_pct":  round(margin, 1),
            "recommended_credits": round(recommended_credits, 1),
            "total_requests_30d":  actual_costs.get(action, {}).get("total_requests", 0),
        })

    # Platform-wide margin estimate
    total_rev  = sum(r["revenue_estimate_usd"] for r in analysis)
    total_cost = sum(r["avg_ai_cost_usd"] for r in analysis)
    platform_margin = ((total_rev - total_cost) / total_rev * 100) if total_rev > 0 else 0

    return {
        "analysis":                   sorted(analysis, key=lambda x: x["total_requests_30d"], reverse=True),
        "revenue_per_credit_usd":     round(revenue_per_credit, 5),
        "target_margin_pct":          int(TARGET_MARGIN * 100),
        "platform_profit_margin_pct": round(platform_margin, 1),
    }


# ---------------------------------------------------------------------------
# Admin Growth Stats
# GET /admin/growth-stats — signups, top users, feature usage, churn, burn rate
# ---------------------------------------------------------------------------

@admin_router.get("/growth-stats")
async def admin_growth_stats(admin: dict = Depends(_require_admin)):
    """
    Growth & engagement stats for the admin dashboard.
    Returns:
      - signups_per_day        : new user registrations per day (last 30 days)
      - pro_users_this_week    : paid users active this week
      - pro_users_last_week    : paid users active last week
      - top_users              : top 10 most active users (all time)
      - features_by_plan       : top 5 actions per plan (this month)
      - churn_estimate         : users with zero activity in past 30 days
      - burn_rate_by_plan      : credits used per plan this month
    """
    from datetime import datetime, timezone as _tz

    db   = _get_db()
    now  = datetime.now(_tz.utc)
    ts   = now.timestamp()
    month_key = f"{now.year:04d}-{now.month:02d}"

    # ── New signups per day — last 30 days ───────────────────────────────────
    thirty_ago = ts - 30 * 86400
    seven_ago  = ts - 7 * 86400
    fourteen_ago = ts - 14 * 86400

    signup_agg = await db["users"].aggregate([
        {"$match": {"created_at": {"$gte": thirty_ago}}},
        {"$group": {
            "_id": {"$dateToString": {
                "format": "%Y-%m-%d",
                "date": {"$toDate": {"$multiply": ["$created_at", 1000]}},
            }},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(30)
    signups_per_day = [{"date": d["_id"], "signups": d["count"]} for d in signup_agg]

    # ── Pro users active this week vs last week ──────────────────────────────
    pro_plans = ["standard", "pro", "max", "team"]

    async def _count_active_paid(since_ts: float, until_ts: float) -> int:
        agg = await db["activity_logs"].aggregate([
            {"$match": {
                "timestamp": {"$gte": since_ts, "$lt": until_ts},
                "plan": {"$in": pro_plans},
            }},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"},
        ]).to_list(1)
        return agg[0]["count"] if agg else 0

    pro_this_week = await _count_active_paid(seven_ago, ts)
    pro_last_week = await _count_active_paid(fourteen_ago, seven_ago)

    # ── Top 10 most active users (all time) ──────────────────────────────────
    top_users_agg = await db["activity_logs"].aggregate([
        {"$group": {
            "_id":      "$user_id",
            "requests": {"$sum": 1},
            "credits":  {"$sum": "$credits_used"},
            "user_name":  {"$last": "$user_name"},
            "user_email": {"$last": "$user_email"},
            "plan":       {"$last": "$plan"},
        }},
        {"$sort": {"requests": -1}},
        {"$limit": 10},
    ]).to_list(10)
    top_users = [
        {
            "name":     r.get("user_name") or r.get("_id", "—"),
            "email":    r.get("user_email") or "—",
            "plan":     r.get("plan") or "free",
            "requests": r.get("requests", 0),
            "credits":  r.get("credits", 0),
        }
        for r in top_users_agg
    ]

    # ── Top 5 features per plan (this month) ─────────────────────────────────
    features_agg = await db["activity_logs"].aggregate([
        {"$match": {"month_key": month_key}},
        {"$group": {
            "_id": {"plan": "$plan", "action": "$action_type"},
            "requests": {"$sum": 1},
        }},
        {"$sort": {"requests": -1}},
    ]).to_list(100)

    features_by_plan: dict = {}
    for r in features_agg:
        plan   = r["_id"].get("plan") or "free"
        action = r["_id"].get("action") or "unknown"
        if plan not in features_by_plan:
            features_by_plan[plan] = []
        if len(features_by_plan[plan]) < 5:
            features_by_plan[plan].append({"action": action, "requests": r["requests"]})

    # ── Churn estimate: registered users with no activity in last 30 days ────
    active_ids_agg = await db["activity_logs"].aggregate([
        {"$match": {"timestamp": {"$gte": thirty_ago}}},
        {"$group": {"_id": "$user_id"}},
    ]).to_list(10000)
    active_ids = {str(r["_id"]) for r in active_ids_agg}

    total_users = await db["users"].count_documents({})
    churn_estimate = max(0, total_users - len(active_ids))

    # ── Credit burn rate per plan (this month) ───────────────────────────────
    burn_agg = await db["activity_logs"].aggregate([
        {"$match": {"month_key": month_key}},
        {"$group": {
            "_id":     "$plan",
            "credits": {"$sum": "$credits_used"},
            "users":   {"$addToSet": "$user_id"},
        }},
    ]).to_list(10)
    burn_rate_by_plan = [
        {
            "plan":           r.get("_id") or "free",
            "total_credits":  r.get("credits", 0),
            "active_users":   len(r.get("users", [])),
            "credits_per_user": round(r.get("credits", 0) / max(1, len(r.get("users", []))), 1),
        }
        for r in sorted(burn_agg, key=lambda x: x.get("credits", 0), reverse=True)
    ]

    return {
        "signups_per_day":    signups_per_day,
        "pro_users_this_week": pro_this_week,
        "pro_users_last_week": pro_last_week,
        "top_users":           top_users,
        "features_by_plan":    features_by_plan,
        "churn_estimate":      churn_estimate,
        "burn_rate_by_plan":   burn_rate_by_plan,
    }


# ---------------------------------------------------------------------------
# Admin Override System
# POST /api/admin/users/{user_id}/unflag          — clear abuse flags
# POST /api/admin/users/{user_id}/reset-enforcement — reset enforcement stage to 0
# POST /api/admin/users/{user_id}/grant-credits    — manually grant credits
# POST /api/admin/users/{user_id}/restore-access   — restore plan + clear block
# ---------------------------------------------------------------------------

class AdminNoteBody(BaseModel):
    note: str = ""

class GrantCreditsBody(BaseModel):
    subscription_credits: Optional[int] = None
    topup_credits: Optional[int] = None
    note: str = ""

class RestoreAccessBody(BaseModel):
    plan: str = "free"
    subscription_credits: Optional[int] = None
    note: str = ""


def _admin_require(authorization: Optional[str] = Header(default=None)):
    """Dependency: require admin role. Raises 403 if not admin."""
    db = _get_db()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@auth_router.post("/admin/users/{user_id}/unflag")
async def admin_unflag_user(
    user_id: str,
    body: AdminNoteBody,
    authorization: Optional[str] = Header(default=None),
):
    """Clear all unactioned abuse flags for a user."""
    db = _get_db()
    caller = _admin_require(authorization)
    caller_uid = caller.get("sub")
    caller_doc = await db["users"].find_one({"id": caller_uid}, {"role": 1})
    if not caller_doc or caller_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    result = await db["abuse_flags"].update_many(
        {"user_id": user_id, "actioned": {"$ne": True}},
        {"$set": {
            "actioned":    True,
            "actioned_by": caller_uid,
            "actioned_at": time.time(),
            "admin_note":  body.note,
        }},
    )
    log.info("Admin %s unflagged user %s (%d flags cleared)", caller_uid, user_id, result.modified_count)
    return {"ok": True, "flags_cleared": result.modified_count, "user_id": user_id}


@auth_router.post("/admin/users/{user_id}/reset-enforcement")
async def admin_reset_enforcement(
    user_id: str,
    body: AdminNoteBody,
    authorization: Optional[str] = Header(default=None),
):
    """Reset enforcement stage to 0 (removes throttle/hard-block)."""
    db = _get_db()
    caller = _admin_require(authorization)
    caller_uid = caller.get("sub")
    caller_doc = await db["users"].find_one({"id": caller_uid}, {"role": 1})
    if not caller_doc or caller_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    await db["user_enforcement"].update_one(
        {"user_id": user_id},
        {"$set": {
            "stage":       0,
            "reset_by":    caller_uid,
            "reset_at":    time.time(),
            "admin_note":  body.note,
        }},
        upsert=True,
    )
    log.info("Admin %s reset enforcement for user %s to stage 0", caller_uid, user_id)
    return {"ok": True, "user_id": user_id, "stage": 0}


@auth_router.post("/admin/users/{user_id}/grant-credits")
async def admin_grant_credits(
    user_id: str,
    body: GrantCreditsBody,
    authorization: Optional[str] = Header(default=None),
):
    """Manually grant subscription_credits and/or topup_credits to a user."""
    db = _get_db()
    caller = _admin_require(authorization)
    caller_uid = caller.get("sub")
    caller_doc = await db["users"].find_one({"id": caller_uid}, {"role": 1})
    if not caller_doc or caller_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    if body.subscription_credits is None and body.topup_credits is None:
        raise HTTPException(status_code=400, detail="Specify subscription_credits and/or topup_credits")

    inc = {}
    if body.subscription_credits is not None and body.subscription_credits > 0:
        inc["subscription_credits"] = body.subscription_credits
    if body.topup_credits is not None and body.topup_credits > 0:
        inc["topup_credits"] = body.topup_credits

    if not inc:
        raise HTTPException(status_code=400, detail="Credit amounts must be positive integers")

    result = await db["users"].find_one_and_update(
        {"id": user_id},
        {"$inc": inc, "$set": {"admin_credit_grant_at": time.time()}},
        return_document=True,
        projection={"subscription_credits": 1, "topup_credits": 1, "plan": 1},
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    await db["activity_logs"].insert_one({
        "user_id":      user_id,
        "type":         "admin_credit_grant",
        "action_type":  "admin_credit_grant",
        "credits_used": -(inc.get("subscription_credits", 0) + inc.get("topup_credits", 0)),
        "month_key":    __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m"),
        "timestamp":    time.time(),
        "details": {
            "granted_by":             caller_uid,
            "subscription_credits":   inc.get("subscription_credits", 0),
            "topup_credits":          inc.get("topup_credits", 0),
            "note":                   body.note,
        },
    })

    log.info(
        "Admin %s granted credits to user %s: sub=%d topup=%d",
        caller_uid, user_id,
        inc.get("subscription_credits", 0), inc.get("topup_credits", 0),
    )
    return {
        "ok":                   True,
        "user_id":              user_id,
        "subscription_credits": result.get("subscription_credits", 0),
        "topup_credits":        result.get("topup_credits", 0),
    }


@auth_router.post("/admin/users/{user_id}/restore-access")
async def admin_restore_access(
    user_id: str,
    body: RestoreAccessBody,
    authorization: Optional[str] = Header(default=None),
):
    """
    Restore a user's access after an enforcement block or auto-downgrade.
    Sets plan, resets enforcement stage to 0, clears abuse flags, resets
    payment_failure_count, and optionally sets subscription_credits.
    """
    db = _get_db()
    caller = _admin_require(authorization)
    caller_uid = caller.get("sub")
    caller_doc = await db["users"].find_one({"id": caller_uid}, {"role": 1})
    if not caller_doc or caller_doc.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    from mini_credits import PLAN_CREDIT_LIMITS   # noqa: PLC0415
    valid_plans = set(PLAN_CREDIT_LIMITS.keys()) | {"max"}
    if body.plan not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Invalid plan '{body.plan}'")

    plan_credits = body.subscription_credits
    if plan_credits is None:
        plan_credits = PLAN_CREDIT_LIMITS.get(body.plan, 50)

    # Update user document
    user_update = {
        "plan":                  body.plan,
        "subscription_credits":  plan_credits,
        "payment_failure_count": 0,
        "admin_restored_by":     caller_uid,
        "admin_restored_at":     time.time(),
    }
    result = await db["users"].find_one_and_update(
        {"id": user_id},
        {"$set": user_update},
        return_document=True,
        projection={"id": 1, "email": 1, "plan": 1},
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")

    # Reset enforcement stage
    await db["user_enforcement"].update_one(
        {"user_id": user_id},
        {"$set": {
            "stage":      0,
            "reset_by":   caller_uid,
            "reset_at":   time.time(),
            "admin_note": body.note or "restore-access",
        }},
        upsert=True,
    )

    # Clear all open abuse flags
    cleared = await db["abuse_flags"].update_many(
        {"user_id": user_id, "actioned": {"$ne": True}},
        {"$set": {
            "actioned":    True,
            "actioned_by": caller_uid,
            "actioned_at": time.time(),
            "admin_note":  body.note or "restore-access",
        }},
    )

    await db["activity_logs"].insert_one({
        "user_id":      user_id,
        "type":         "admin_restore_access",
        "action_type":  "admin_restore_access",
        "credits_used": 0,
        "timestamp":    time.time(),
        "details": {
            "restored_by":   caller_uid,
            "plan":          body.plan,
            "credits":       plan_credits,
            "flags_cleared": cleared.modified_count,
            "note":          body.note,
        },
    })

    log.info(
        "Admin %s restored access for user %s → plan=%s credits=%d flags_cleared=%d",
        caller_uid, user_id, body.plan, plan_credits, cleared.modified_count,
    )
    return {
        "ok":                   True,
        "user_id":              user_id,
        "plan":                 body.plan,
        "subscription_credits": plan_credits,
        "enforcement_stage":    0,
        "flags_cleared":        cleared.modified_count,
    }


# ---------------------------------------------------------------------------
# One-time admin bootstrap — swap roles so miniassistantai is admin
# Protected by JWT_SECRET so only someone with server access can call it.
# ---------------------------------------------------------------------------
class BootstrapBody(BaseModel):
    secret: str

@auth_router.post("/admin-bootstrap")
async def admin_bootstrap(body: BootstrapBody):
    """
    One-time endpoint: sets miniassistantai@gmail.com as admin
    and aceelnene@gmail.com as user.
    Requires the JWT_SECRET as the 'secret' field.
    """
    if body.secret != JWT_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    db = _get_db()

    results = {}

    r1 = await db["users"].update_one(
        {"email": "miniassistantai@gmail.com"},
        {"$set": {"role": "admin"}},
    )
    results["miniassistantai"] = "admin" if r1.matched_count else "not found"

    r2 = await db["users"].update_one(
        {"email": "aceelnene@gmail.com"},
        {"$set": {"role": "user"}},
    )
    results["aceelnene"] = "user" if r2.matched_count else "not found"

    return {"ok": True, "results": results}


# ---------------------------------------------------------------------------
# Test email route — GET /api/auth/test-email
# Remove or restrict this in production after confirming delivery.
# ---------------------------------------------------------------------------

@auth_router.get("/test-email")
async def test_email():
    """Send a test welcome email and return the actual Resend response."""
    import resend as _resend  # noqa: PLC0415
    from email_service import SENDER, _build_html  # noqa: PLC0415

    if not _resend.api_key:
        return {"status": "error", "detail": "RESEND_API_KEY not set"}

    params = {
        "from":    SENDER,
        "to":      ["miniassistantai@gmail.com"],
        "subject": "Mini Assistant — Email Test",
        "html":    _build_html("Test User"),
    }
    try:
        result = _resend.Emails.send(params)
        return {"status": "ok", "resend_id": result.get("id"), "sender": SENDER}
    except Exception as exc:
        return {"status": "error", "detail": str(exc), "sender": SENDER}


# ---------------------------------------------------------------------------
# Admin: email analytics — GET /api/admin/email-analytics
# ---------------------------------------------------------------------------

@admin_router.get("/email-analytics")
async def email_analytics(admin: dict = Depends(_require_admin)):
    """
    Returns aggregate email send stats for admins.
    Includes totals, per-type breakdown, conversion counts and rates.
    """
    db = _get_db()

    try:
        # --- Totals ---
        pipeline_totals = [
            {"$group": {
                "_id":       "$status",
                "count":     {"$sum": 1},
            }}
        ]
        totals_raw = await db["email_logs"].aggregate(pipeline_totals).to_list(None)
        totals = {row["_id"]: row["count"] for row in totals_raw}

        total_sent   = totals.get("sent", 0)
        total_failed = totals.get("failed", 0)
        total_all    = total_sent + total_failed

        # --- Per-type breakdown ---
        pipeline_by_type = [
            {"$group": {
                "_id": {
                    "type":   "$email_type",
                    "status": "$status",
                },
                "count": {"$sum": 1},
            }}
        ]
        by_type_raw = await db["email_logs"].aggregate(pipeline_by_type).to_list(None)

        by_type: dict = {}
        for row in by_type_raw:
            t = row["_id"]["type"]
            s = row["_id"]["status"]
            if t not in by_type:
                by_type[t] = {"sent": 0, "failed": 0}
            by_type[t][s] = row["count"]

        # --- Conversions ---
        total_converted = await db["email_logs"].count_documents({"converted": True})
        by_conversion_type_raw = await db["email_logs"].aggregate([
            {"$match": {"converted": True}},
            {"$group": {"_id": "$conversion_type", "count": {"$sum": 1}}},
        ]).to_list(None)
        conversions_by_type = {r["_id"]: r["count"] for r in by_conversion_type_raw}

        conversion_rate = round(total_converted / total_sent * 100, 1) if total_sent else 0

        # --- 7-day daily stats ---
        seven_days_ago = __import__("time").time() - (7 * 86400)
        daily_pipeline = [
            {"$match": {"timestamp": {"$gte": seven_days_ago}}},
            {"$addFields": {
                "day": {"$dateToString": {
                    "format": "%Y-%m-%d",
                    "date":   {"$toDate": {"$multiply": ["$timestamp", 1000]}},
                }}
            }},
            {"$group": {
                "_id":    "$day",
                "sent":   {"$sum": {"$cond": [{"$eq": ["$status", "sent"]},   1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            }},
            {"$sort": {"_id": 1}},
        ]
        daily_raw = await db["email_logs"].aggregate(daily_pipeline).to_list(None)
        daily_stats = [{"date": r["_id"], "sent": r["sent"], "failed": r["failed"]} for r in daily_raw]

        return {
            "total_sent":         total_sent,
            "total_failed":       total_failed,
            "total_emails":       total_all,
            "total_converted":    total_converted,
            "conversion_rate_pct": conversion_rate,
            "conversions_by_type": conversions_by_type,
            "by_type":            by_type,
            "daily_stats_7d":     daily_stats,
        }

    except Exception as exc:
        log.error("email-analytics error: %s", exc)
        return {
            "total_sent": 0, "total_failed": 0, "total_emails": 0,
            "total_converted": 0, "conversion_rate_pct": 0,
            "conversions_by_type": {}, "by_type": {}, "daily_stats_7d": [],
        }


# ---------------------------------------------------------------------------
# Admin: email logs — GET /api/admin/email-logs
# ---------------------------------------------------------------------------

@admin_router.get("/email-logs")
async def email_logs_list(
    type: str = None,
    status: str = None,
    user_id: str = None,
    admin: dict = Depends(_require_admin),
):
    """
    Returns the latest 100 email log entries, newest first.
    Optional query params: type, status, user_id
    """
    db = _get_db()

    query: dict = {}
    if type:
        query["email_type"] = type
    if status:
        query["status"] = status
    if user_id:
        query["user_id"] = user_id

    try:
        cursor = db["email_logs"].find(
            query,
            {"_id": 0},
        ).sort("timestamp", -1).limit(100)

        logs = await cursor.to_list(None)
        return {"logs": logs, "count": len(logs)}

    except Exception as exc:
        log.error("email-logs error: %s", exc)
        return {"logs": [], "count": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Admin: email growth analytics — GET /api/admin/email-growth-analytics
# ---------------------------------------------------------------------------

@admin_router.get("/email-growth-analytics")
async def email_growth_analytics(admin: dict = Depends(_require_admin)):
    """A/B test results, sequence funnel, revenue attribution, weight snapshot, and LTV analytics."""
    db = _get_db()
    from email_growth import (          # noqa: PLC0415
        get_ab_analytics,
        get_sequence_analytics,
        get_revenue_analytics,
        get_ab_weights_snapshot,
        get_ltv_analytics,
    )
    ab, seq, rev, weights, ltv = await asyncio.gather(
        get_ab_analytics(db),
        get_sequence_analytics(db),
        get_revenue_analytics(db),
        get_ab_weights_snapshot(db),
        get_ltv_analytics(db),
        return_exceptions=True,
    )
    return {
        "ab_testing":  ab      if not isinstance(ab,      Exception) else {},
        "sequences":   seq     if not isinstance(seq,     Exception) else {},
        "revenue":     rev     if not isinstance(rev,     Exception) else {},
        "ab_weights":  weights if not isinstance(weights, Exception) else {},
        "ltv":         ltv     if not isinstance(ltv,     Exception) else {},
    }
