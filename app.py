import os, re, logging
from datetime import timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

load_dotenv()

def int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    cleaned = (raw or "").strip()
    try:
        return int(cleaned)
    except ValueError:
        m = re.search(r'\d+', cleaned)
        if m:
            logging.warning("Coercing %s from %r to %s", name, raw, m.group(0))
            return int(m.group(0))
        logging.warning("Falling back to default for %s: %r", name, raw)
        return default

def bool_env(name: str, default: bool=False) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    return raw in {"1","true","t","yes","y","on"}

# ----- Flask setup
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
app.config.update(
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///mcw.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    REMEMBER_COOKIE_DURATION=timedelta(days=30),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    PREFERRED_URL_SCHEME=os.getenv("PREFERRED_URL_SCHEME", "https"),
    ASSET_VERSION=os.getenv("ASSET_VERSION", "v1"),
)

# Mail backend selection (resend → smtp → echo → disabled)
from mailer import Mailer
mailer = Mailer(
    resend_api_key=os.getenv("RESEND_API_KEY"),
    resend_from=os.getenv("RESEND_FROM"),
    smtp_host=os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER"),
    smtp_port=int_env("SMTP_PORT", 587),
    smtp_user=os.getenv("SMTP_USER"),
    smtp_pass=os.getenv("SMTP_PASS"),
    smtp_from=os.getenv("SMTP_FROM"),
    use_tls=bool_env("SMTP_USE_TLS", True),
    dev_echo=bool_env("DEV_MAIL_ECHO", False),
)

# DB + User model
from models import db, User, password_valid
db.init_app(app)

with app.app_context():
    db.create_all()

# Login manager
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

# Token utils
def token_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="mcw-password-reset")

def abs_url(path: str) -> str:
    base = os.getenv("APP_BASE_URL")  # e.g., https://mini-casino.world
    if base:
        return base.rstrip("/") + path
    return url_for("intro", _external=True).replace("/intro","") + path

# ----- Routes

@app.get("/")
def root():
    return redirect(url_for("intro") if current_user.is_authenticated else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pw):
            login_user(user, remember=True)
            return redirect(url_for("intro"))
        flash("Invalid email or password.", "error")
    return render_template("login.html", title="Sign in • MCW")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        agree = request.form.get("agree_terms")
        if not password_valid(pw):
            flash("Password must be at least 8 chars and include a letter & a number.", "error")
        elif not agree:
            flash("Please accept the terms.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
        else:
            u = User(email=email)
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            login_user(u, remember=True)
            return redirect(url_for("intro"))
    return render_template("register.html", title="Create account • MCW")

@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/reset", methods=["GET","POST"])
def reset_request():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            s = token_serializer()
            token = s.dumps({"uid": user.id, "email": user.email})
            link = abs_url(url_for("reset_token", token=token))
            mailer.send(
                to=email,
                subject="MCW password reset",
                text=f"Reset your password: {link}",
                html=f"<p>Reset your password:</p><p><a href='{link}'>{link}</a></p>",
            )
        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("login"))
    return render_template("reset_request.html", title="Reset password • MCW")

@app.route("/reset/<token>", methods=["GET","POST"])
def reset_token(token):
    s = token_serializer()
    try:
        data = s.loads(token, max_age=int_env("PASSWORD_RESET_TOKEN_MAX_AGE", 3600))
        user = db.session.get(User, int(data["uid"]))
    except (BadSignature, SignatureExpired, KeyError):
        user = None
    if not user:
        flash("Reset link is invalid or expired.", "error")
        return redirect(url_for("reset_request"))

    if request.method == "POST":
        pw = request.form.get("password") or ""
        pw2 = request.form.get("confirm_password") or ""
        if pw != pw2:
            flash("Passwords do not match.", "error")
        elif not password_valid(pw):
            flash("Password must be at least 8 chars and include a letter & a number.", "error")
        else:
            user.set_password(pw)
            db.session.commit()
            flash("Password updated. Please sign in.", "success")
            return redirect(url_for("login"))

    return render_template("reset_token.html", title="Choose a new password • MCW", token=token)

@app.get("/intro")
@login_required
def intro():
    return render_template("intro.html", title="Mini Casino World")

# Optional: dev-only diagnostic
if os.getenv("ENABLE_DIAG_MAIL") == "1" and os.getenv("FLASK_ENV") != "production":
    @app.get("/__diag/mail")
    def __diag_mail():
        return jsonify(mailer.describe()), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int_env("PORT", 5000), debug=bool_env("FLASK_DEBUG", False))