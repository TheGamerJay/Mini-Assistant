import os, random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from sqlalchemy import create_engine, Column, BigInteger, String, Numeric, Boolean, TIMESTAMP, ForeignKey, JSON, func, desc
from sqlalchemy.orm import declarative_base, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------- ENV / CONFIG ----------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set")

# Configurable bet caps and bonus
MAX_BET_BLACKJACK = float(os.getenv("MAX_BET_BLACKJACK", "10000"))
MAX_BET_ROULETTE  = float(os.getenv("MAX_BET_ROULETTE", "10000"))
MAX_BET_SLOTS     = float(os.getenv("MAX_BET_SLOTS", "10000"))
DAILY_BONUS_CHIPS = float(os.getenv("DAILY_BONUS_CHIPS", "500"))

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = SECRET_KEY
app.config["JSON_SORT_KEYS"] = False

CORS(app, supports_credentials=True)
jwt = JWTManager(app)

# ---------------------- DB SETUP --------------------------
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

# ---------------------- MODELS ----------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    balance = Column(Numeric(12,2), nullable=False, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow)

class Game(Base):
    __tablename__ = "games"
    id = Column(BigInteger, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(50), nullable=False)
    house_edge = Column(Numeric(5,2))
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

class Bet(Base):
    __tablename__ = "bets"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_id = Column(BigInteger, ForeignKey("games.id", ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(12,2), nullable=False)
    outcome = Column(String(20))      # win / lose / push
    payout = Column(Numeric(12,2), default=0)
    result_meta = Column(JSON)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(12,2), nullable=False)
    type = Column(String(20), nullable=False)      # deposit | purchase_chips | adjust
    status = Column(String(20), nullable=False, default="completed")
    ref_code = Column(String(64))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    daily_loss_limit = Column(Numeric(12,2))       # nullable = no limit
    daily_deposit_limit = Column(Numeric(12,2))    # nullable = no limit
    last_bonus_at = Column(TIMESTAMP)              # for daily bonus timestamp

# ---------------------- BOOTSTRAP -------------------------
def ensure_tables_and_games():
    # Create all tables first
    Base.metadata.create_all(bind=engine)

    # Then ensure games exist
    s = SessionLocal()
    try:
        catalog = [
            ("Blackjack", "blackjack"),
            ("Roulette Red/Black", "roulette"),
            ("Slots – Chips Only", "slots"),
        ]
        for name, gtype in catalog:
            if not s.query(Game).filter_by(name=name).first():
                s.add(Game(name=name, type=gtype))
        s.commit()
    finally:
        s.close()

ensure_tables_and_games()

# ---------------------- HELPERS ---------------------------
def as_money(x) -> float:
    # Normalize Decimals/Numerics to float for JSON
    if isinstance(x, Decimal):
        return float(x)
    return float(Decimal(str(x)))

def get_user(s, identity):
    u = s.query(User).filter(User.id == int(identity), User.is_active.is_(True)).first()
    if not u: raise ValueError("user_not_found_or_inactive")
    return u

def get_game(s, gtype):
    g = s.query(Game).filter(Game.type == gtype, Game.is_active.is_(True)).first()
    if not g: raise ValueError("game_not_active")
    return g

def debit(s, u, amt):
    if as_money(u.balance) < amt: raise ValueError("insufficient_balance")
    u.balance = Decimal(str(as_money(u.balance) - amt)); s.flush()

def credit(s, u, amt):
    u.balance = Decimal(str(as_money(u.balance) + amt)); s.flush()

def get_settings(s, user_id: int):
    us = s.get(UserSettings, user_id)
    if not us:
        us = UserSettings(user_id=user_id)
        s.add(us); s.flush()
    return us

def today_bounds_utc():
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end

def user_today_net_loss(s, user_id: int) -> float:
    start, end = today_bounds_utc()
    # Loss = sum(bet - payout) where bet>payout
    rows = (
        s.query(func.coalesce(func.sum((Bet.amount - Bet.payout)), 0))
        .filter(Bet.user_id == user_id, Bet.created_at >= start, Bet.created_at < end)
        .all()
    )
    gross = float(rows[0][0] or 0)
    return max(gross, 0.0)

# ---------------------- AUTH ------------------------------
@app.post("/api/auth/register")
def register():
    d = request.get_json(force=True)
    username = (d.get("username") or "").strip()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    if not username or not email or not password: return {"error":"missing_fields"},400
    if len(password) < 6: return {"error":"weak_password"},400

    s = SessionLocal()
    try:
        if s.query(User).filter((User.username==username)|(User.email==email)).first():
            return {"error":"user_exists"},409
        u = User(username=username, email=email, password_hash=generate_password_hash(password), balance=Decimal("0.00"))
        s.add(u); s.commit()
        token = create_access_token(identity=str(u.id), expires_delta=timedelta(days=7))
        return {"access_token":token, "user":{"id":u.id,"username":u.username,"email":u.email}},201
    finally:
        s.close()

@app.post("/api/auth/login")
def login():
    d = request.get_json(force=True)
    ident = (d.get("identifier") or "").strip()
    pw = d.get("password") or ""
    if not ident or not pw: return {"error":"missing_fields"},400
    s = SessionLocal()
    try:
        u = s.query(User).filter((User.email==ident.lower())|(User.username==ident)).first()
        if not u or not check_password_hash(u.password_hash, pw): return {"error":"invalid_credentials"},401
        if not u.is_active: return {"error":"inactive_user"},403
        token = create_access_token(identity=str(u.id), expires_delta=timedelta(days=7))
        return {"access_token":token, "user":{"id":u.id,"username":u.username,"email":u.email}}
    finally:
        s.close()

# ---------------------- PROFILE ---------------------------
@app.get("/api/users/me")
@jwt_required()
def me():
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        return {"user":{"id":u.id,"username":u.username,"email":u.email,"created_at":u.created_at.isoformat()}}
    finally:
        s.close()

@app.put("/api/users/me")
@jwt_required()
def update_me():
    d = request.get_json(force=True)
    new_username = (d.get("username") or "").strip()
    if not new_username: return {"error":"missing_username"},400
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        # ensure unique
        taken = s.query(User).filter(User.username==new_username, User.id!=u.id).first()
        if taken: return {"error":"username_taken"},409
        u.username = new_username; s.commit()
        return {"user":{"id":u.id,"username":u.username,"email":u.email}}
    finally:
        s.close()

# ---------------------- SETTINGS & BONUS ------------------
@app.get("/api/users/me/settings")
@jwt_required()
def get_user_settings():
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        us = get_settings(s, u.id)
        return {
            "daily_loss_limit": as_money(us.daily_loss_limit) if us.daily_loss_limit is not None else None,
            "daily_deposit_limit": as_money(us.daily_deposit_limit) if us.daily_deposit_limit is not None else None,
            "last_bonus_at": us.last_bonus_at.isoformat() if us.last_bonus_at else None,
        }
    finally:
        s.close()

@app.put("/api/users/me/settings")
@jwt_required()
def put_user_settings():
    d = request.get_json(force=True)
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        us = get_settings(s, u.id)
        if "daily_loss_limit" in d:
            v = d["daily_loss_limit"]
            us.daily_loss_limit = None if v in ("", None) else Decimal(str(v))
        if "daily_deposit_limit" in d:
            v = d["daily_deposit_limit"]
            us.daily_deposit_limit = None if v in ("", None) else Decimal(str(v))
        s.commit()
        return {"ok": True}
    finally:
        s.close()

@app.post("/api/bonus/daily")
@jwt_required()
def claim_daily_bonus():
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        us = get_settings(s, u.id)
        now = datetime.now(timezone.utc)
        if us.last_bonus_at and (now - us.last_bonus_at) < timedelta(hours=24):
            return {"error": "bonus_already_claimed"}, 400
        credit(s, u, DAILY_BONUS_CHIPS)
        us.last_bonus_at = now
        s.add(Transaction(user_id=u.id, amount=Decimal(str(DAILY_BONUS_CHIPS)), type="adjust", status="completed", ref_code="daily_bonus"))
        s.commit()
        return {"ok": True, "bonus": DAILY_BONUS_CHIPS, "balance": as_money(u.balance)}
    finally:
        s.close()

# ---------------------- WALLET ----------------------------
@app.get("/api/users/me/balance")
@jwt_required()
def my_balance():
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        return {"balance": as_money(u.balance)}
    finally:
        s.close()

@app.post("/api/wallet/deposit")
@jwt_required()
def deposit():
    d = request.get_json(force=True)
    try:
        amount = Decimal(str(d.get("amount")))
    except Exception:
        return {"error":"invalid_amount"},400
    if amount <= 0: return {"error":"amount_must_be_positive"},400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        us = get_settings(s, u.id)

        # Enforce daily deposit limit if set
        if us.daily_deposit_limit is not None:
            start, end = today_bounds_utc()
            deposited_today = s.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
                Transaction.user_id == u.id,
                Transaction.type.in_(["deposit", "purchase_chips"]),
                Transaction.created_at >= start, Transaction.created_at < end
            ).scalar() or 0
            projected = float(deposited_today) + float(amount)
            if projected > float(us.daily_deposit_limit):
                return {"error": "deposit_limit_reached"}, 403

        credit(s, u, as_money(amount))
        s.add(Transaction(user_id=u.id, amount=amount, type="deposit", status="completed"))
        s.commit()
        return {"ok":True, "balance":as_money(u.balance)}
    except ValueError as e:
        s.rollback(); return {"error":str(e)},400
    finally:
        s.close()

# ---------------------- STORE -----------------------------
# Real products (chip packs). Purchasing credits chips and logs a transaction.
PRODUCTS = [
    {"id":"chips_1k","name":"Starter Pack","subtitle":"Great for warm-up","chips":1000},
    {"id":"chips_5k","name":"High Roller","subtitle":"Go bigger","chips":5000},
    {"id":"chips_20k","name":"Whale Pack","subtitle":"Own the table","chips":20000},
]

@app.get("/api/store/products")
@jwt_required()
def store_products():
    return jsonify(PRODUCTS)

@app.post("/api/store/checkout")
@jwt_required()
def store_checkout():
    d = request.get_json(force=True)
    pid = d.get("product_id")
    prod = next((p for p in PRODUCTS if p["id"]==pid), None)
    if not prod: return {"error":"invalid_product"},400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        chips = Decimal(str(prod["chips"]))
        credit(s, u, as_money(chips))
        s.add(Transaction(user_id=u.id, amount=chips, type="purchase_chips", status="completed", ref_code=pid))
        s.commit()
        return {"ok":True, "product":prod, "balance":as_money(u.balance)}
    except ValueError as e:
        s.rollback(); return {"error":str(e)},400
    finally:
        s.close()

# ---------------------- GAMES: Blackjack / Slots / Roulette ----------------------
RANKS = list(range(2, 11)) + ['J','Q','K','A']
SUITS = ['♠','♥','♦','♣']
def fresh_shoe():
    import random as _r
    deck=[(r,s) for r in RANKS for s in SUITS]*6; _r.shuffle(deck); return deck
def hand_value(cards):
    total, aces = 0, 0
    for r,_ in cards:
        if isinstance(r,int): total += r
        elif r in ['J','Q','K']: total += 10
        else: total += 11; aces += 1
    while total>21 and aces: total -= 10; aces -= 1
    return total
def play_dealer(deck, dealer):
    while hand_value(dealer) < 17: dealer.append(deck.pop())

@app.post("/api/blackjack/play")
@jwt_required()
def blackjack_play():
    d = request.get_json(force=True)
    try: bet = Decimal(str(d.get("bet")))
    except Exception: return {"error":"invalid_bet"},400
    if bet <= 0: return {"error":"bet_must_be_positive"},400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        us = get_settings(s, u.id)

        # Bet size cap
        if float(bet) > MAX_BET_BLACKJACK:
            return {"error": f"max_bet_blackjack_{int(MAX_BET_BLACKJACK)}"}, 400

        # Daily loss limit enforcement (pre-check)
        if us.daily_loss_limit is not None:
            if user_today_net_loss(s, u.id) + float(bet) > float(us.daily_loss_limit):
                return {"error": "loss_limit_reached"}, 403

        g = get_game(s, "blackjack")
        debit(s, u, as_money(bet))
        deck = fresh_shoe(); player=[deck.pop(),deck.pop()]; dealer=[deck.pop(),deck.pop()]
        while hand_value(player) < 17: player.append(deck.pop())
        play_dealer(deck, dealer)
        pv, dv = hand_value(player), hand_value(dealer)
        if pv>21: outcome, payout = "lose", Decimal("0")
        elif dv>21 or pv>dv:
            payout = bet * (Decimal("2.5") if (len(player)==2 and pv==21) else Decimal("2.0"))
            outcome = "win"; credit(s, u, as_money(payout))
        elif pv==dv:
            payout = bet; outcome = "push"; credit(s, u, as_money(payout))
        else: outcome, payout = "lose", Decimal("0")
        s.add(Bet(user_id=u.id, game_id=g.id, amount=bet, outcome=outcome, payout=payout, result_meta={"player":player,"dealer":dealer,"player_value":pv,"dealer_value":dv}))
        s.commit()
        return {"ok":True,"outcome":outcome,"payout":as_money(payout),"balance":as_money(u.balance),"cards":{"player":player,"dealer":dealer,"player_value":pv,"dealer_value":dv}}
    except ValueError as e:
        s.rollback(); return {"error":str(e)},400
    except Exception:
        s.rollback(); return {"error":"server_error"},500
    finally:
        s.close()

SLOTS_REEL = ["7","BAR","🍒","💎","🔔","⭐","🍋"]
PAYTABLE = { ("7","7","7"):50, ("BAR","BAR","BAR"):20, ("💎","💎","💎"):10, ("🍒","🍒","🍒"):8, ("🔔","🔔","🔔"):6, ("⭐","⭐","⭐"):4, ("🍋","🍋","🍋"):3, "ANY_CHERRY":2 }

def slots_symbols():
    import random as _r
    return [_r.choice(SLOTS_REEL) for _ in range(3)]

def slots_multiplier(symbols):
    tup=tuple(symbols)
    if tup in PAYTABLE: return PAYTABLE[tup]
    if symbols.count("🍒")==2: return 3
    if symbols.count("🍒")==1: return PAYTABLE["ANY_CHERRY"]
    return 0

@app.post("/api/slots/spin")
@jwt_required()
def slots_spin():
    d = request.get_json(force=True)
    try: bet = Decimal(str(d.get("bet")))
    except Exception: return {"error":"invalid_bet"},400
    if bet <= 0: return {"error":"bet_must_be_positive"},400
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        us = get_settings(s, u.id)

        # Bet size cap
        if float(bet) > MAX_BET_SLOTS:
            return {"error": f"max_bet_slots_{int(MAX_BET_SLOTS)}"}, 400

        # Daily loss limit enforcement (pre-check)
        if us.daily_loss_limit is not None:
            if user_today_net_loss(s, u.id) + float(bet) > float(us.daily_loss_limit):
                return {"error": "loss_limit_reached"}, 403

        g = get_game(s, "slots")
        debit(s, u, as_money(bet))
        symbols = slots_symbols(); mult = slots_multiplier(symbols)
        payout = bet * Decimal(str(mult)); outcome = "win" if payout>0 else "lose"
        if payout>0: credit(s, u, as_money(payout))
        s.add(Bet(user_id=u.id, game_id=g.id, amount=bet, outcome=outcome, payout=payout, result_meta={"symbols":symbols,"multiplier":mult}))
        s.commit()
        return {"ok":True,"outcome":outcome,"symbols":symbols,"multiplier":mult,"payout":as_money(payout),"balance":as_money(u.balance)}
    except ValueError as e:
        s.rollback(); return {"error":str(e)},400
    except Exception:
        s.rollback(); return {"error":"server_error"},500
    finally:
        s.close()

# Roulette
RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
BLACK_NUMS = set(range(1,37)) - RED_NUMS

def spin_wheel():
    import random as _r
    return _r.randint(0,36)

@app.post("/api/roulette/bet")
@jwt_required()
def roulette_bet():
    d = request.get_json(force=True)
    color = (d.get("color") or "").lower()
    if color not in ("red","black"): return {"error":"color_must_be_red_or_black"},400
    try: bet = Decimal(str(d.get("bet")))
    except Exception: return {"error":"invalid_bet"},400
    if bet <= 0: return {"error":"bet_must_be_positive"},400
    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        us = get_settings(s, u.id)

        # Bet size cap
        if float(bet) > MAX_BET_ROULETTE:
            return {"error": f"max_bet_roulette_{int(MAX_BET_ROULETTE)}"}, 400

        # Daily loss limit enforcement (pre-check)
        if us.daily_loss_limit is not None:
            if user_today_net_loss(s, u.id) + float(bet) > float(us.daily_loss_limit):
                return {"error": "loss_limit_reached"}, 403

        g = get_game(s, "roulette")
        debit(s, u, as_money(bet))
        n = spin_wheel()
        won = (n in RED_NUMS and color=="red") or (n in BLACK_NUMS and color=="black")
        payout = bet * Decimal("2.0") if won else Decimal("0")
        if payout>0: credit(s, u, as_money(payout))
        outcome = "win" if won else "lose"
        res_color = "green" if n==0 else ("red" if n in RED_NUMS else "black")
        s.add(Bet(user_id=u.id, game_id=g.id, amount=bet, outcome=outcome, payout=payout, result_meta={"number":n,"color":res_color}))
        s.commit()
        return {"ok":True,"outcome":outcome,"roll":n,"roll_color":res_color,"payout":as_money(payout),"balance":as_money(u.balance)}
    except ValueError as e:
        s.rollback(); return {"error":str(e)},400
    except Exception:
        s.rollback(); return {"error":"server_error"},500
    finally:
        s.close()

# ---------------------- COMMUNITY: Leaderboard ------------
@app.get("/api/leaderboard")
@jwt_required()
def leaderboard():
    window = (request.args.get("window") or "all").lower()
    s = SessionLocal()
    try:
        q = s.query(
            User.id.label("user_id"),
            User.username.label("username"),
            func.coalesce(func.sum(Bet.payout - Bet.amount), 0).label("net_winnings")
        ).outerjoin(Bet, Bet.user_id == User.id)

        if window in ("7d","30d"):
            days = 7 if window == "7d" else 30
            after = datetime.utcnow() - timedelta(days=days)
            q = q.filter(Bet.created_at >= after)

        q = q.group_by(User.id, User.username).order_by(func.coalesce(func.sum(Bet.payout - Bet.amount), 0).desc()).limit(100)
        res = [{"user_id": r.user_id, "username": r.username, "net_winnings": as_money(r.net_winnings)} for r in q.all()]
        return jsonify(res)
    finally:
        s.close()

# ---------------------- HISTORY ---------------------------
@app.get("/api/history/bets")
@jwt_required()
def history_bets():
    """Return recent bets for the authenticated user, newest first."""
    try:
        limit = max(1, min(int(request.args.get("limit", 25)), 100))
        offset = max(0, int(request.args.get("offset", 0)))
    except Exception:
        return {"error": "bad_pagination"}, 400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        q = (
            s.query(
                Bet.id, Bet.amount, Bet.payout, Bet.outcome, Bet.created_at, Game.type.label("game_type")
            )
            .join(Game, Game.id == Bet.game_id)
            .filter(Bet.user_id == u.id)
            .order_by(desc(Bet.created_at))
            .limit(limit).offset(offset)
        )
        rows = [{
            "id": r.id,
            "amount": as_money(r.amount),
            "payout": as_money(r.payout),
            "outcome": r.outcome,
            "created_at": r.created_at.isoformat(),
            "game_type": r.game_type
        } for r in q.all()]
        return rows
    finally:
        s.close()

@app.get("/api/history/transactions")
@jwt_required()
def history_transactions():
    """Return recent wallet/store transactions for the authenticated user."""
    try:
        limit = max(1, min(int(request.args.get("limit", 25)), 100))
        offset = max(0, int(request.args.get("offset", 0)))
    except Exception:
        return {"error": "bad_pagination"}, 400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        q = (
            s.query(Transaction.id, Transaction.type, Transaction.amount, Transaction.ref_code, Transaction.created_at)
            .filter(Transaction.user_id == u.id)
            .order_by(desc(Transaction.created_at))
            .limit(limit).offset(offset)
        )
        rows = [{
            "id": r.id,
            "type": r.type,
            "amount": as_money(r.amount),
            "ref_code": r.ref_code,
            "created_at": r.created_at.isoformat()
        } for r in q.all()]
        return rows
    finally:
        s.close()

# ---------------------- ROUTES ----------------------------
@app.get("/intro")
def intro():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Mini Casino World</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #1e1e1e, #2d2d2d); color: white; min-height: 100vh; }
        .container { max-width: 800px; margin: 0 auto; text-align: center; }
        h1 { color: #ff6b6b; font-size: 3em; margin-bottom: 20px; }
        p { font-size: 1.2em; margin-bottom: 30px; }
        .cta { background: #ff6b6b; color: white; padding: 15px 30px; text-decoration: none; border-radius: 10px; font-size: 1.1em; display: inline-block; }
        .cta:hover { background: #ff5252; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎰 Mini Casino World</h1>
        <p>Experience the thrill of casino gaming with Blackjack, Roulette, and Slots!</p>
        <p>Features include:</p>
        <ul style="text-align: left; display: inline-block; font-size: 1.1em;">
            <li>🃏 Classic Blackjack (21 vs House)</li>
            <li>🎯 Red/Black Roulette</li>
            <li>🎰 Lucky Slots</li>
            <li>💰 Chip Store & Daily Bonuses</li>
            <li>🏆 Community Leaderboards</li>
            <li>⚖️ Responsible Gaming Limits</li>
        </ul>
        <p><a href="/" class="cta">Enter Casino</a></p>
    </div>
</body>
</html>"""

@app.get("/")
def index():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Mini Casino World</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://unpkg.com/react@18/umd/react.development.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel" src="/static/MiniCasinoUI.jsx"></script>
</body>
</html>"""

# ---------------------- HEALTH ----------------------------
@app.get("/healthz")
def health():
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=True)