import os, random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Numeric, Boolean,
    TIMESTAMP, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------- ENV / CONFIG ----------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is not set")

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

def get_user(session, identity) -> User:
    u = session.query(User).filter(User.id == int(identity), User.is_active.is_(True)).first()
    if not u:
        raise ValueError("user_not_found_or_inactive")
    return u

def get_game(session, gtype: str) -> Game:
    g = session.query(Game).filter(Game.type == gtype, Game.is_active.is_(True)).first()
    if not g:
        raise ValueError("game_not_active")
    return g

def debit(session, user: User, amt: float):
    if as_money(user.balance) < amt:
        raise ValueError("insufficient_balance")
    user.balance = Decimal(str(as_money(user.balance) - amt))
    session.flush()

def credit(session, user: User, amt: float):
    user.balance = Decimal(str(as_money(user.balance) + amt))
    session.flush()

# ---------------------- AUTH ------------------------------
@app.post("/api/auth/register")
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not email or not password:
        return {"error": "missing_fields"}, 400
    if len(password) < 6:
        return {"error": "weak_password"}, 400

    s = SessionLocal()
    try:
        if s.query(User).filter((User.username == username)|(User.email == email)).first():
            return {"error": "user_exists"}, 409
        u = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            balance=Decimal("0.00")
        )
        s.add(u)
        s.commit()
        # Issue token
        token = create_access_token(identity=str(u.id), expires_delta=timedelta(days=7))
        return {"access_token": token, "user": {"id": u.id, "username": u.username, "email": u.email}}, 201
    finally:
        s.close()

@app.post("/api/auth/login")
def login():
    data = request.get_json(force=True)
    email_or_username = (data.get("identifier") or "").strip()
    password = data.get("password") or ""
    if not email_or_username or not password:
        return {"error": "missing_fields"}, 400

    s = SessionLocal()
    try:
        q = s.query(User).filter(
            (User.email == email_or_username.lower()) | (User.username == email_or_username)
        ).first()
        if not q or not check_password_hash(q.password_hash, password):
            return {"error": "invalid_credentials"}, 401
        if not q.is_active:
            return {"error": "inactive_user"}, 403
        token = create_access_token(identity=str(q.id), expires_delta=timedelta(days=7))
        return {"access_token": token, "user": {"id": q.id, "username": q.username, "email": q.email}}
    finally:
        s.close()

# ---------------------- PROFILE / WALLET ------------------
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
    data = request.get_json(force=True)
    try:
        amount = Decimal(str(data.get("amount")))
    except Exception:
        return {"error": "invalid_amount"}, 400
    if amount <= 0:
        return {"error": "amount_must_be_positive"}, 400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        credit(s, u, as_money(amount))
        s.commit()
        return {"ok": True, "balance": as_money(u.balance)}
    except ValueError as e:
        s.rollback()
        return {"error": str(e)}, 400
    finally:
        s.close()

# ---------------------- GAMES: BLACKJACK ------------------
RANKS = list(range(2, 11)) + ['J','Q','K','A']
SUITS = ['♠','♥','♦','♣']

def fresh_shoe():
    deck = [(r,s) for r in RANKS for s in SUITS] * 6
    random.shuffle(deck)
    return deck

def hand_value(cards):
    total, aces = 0, 0
    for r,_ in cards:
        if isinstance(r, int):
            total += r
        elif r in ['J','Q','K']:
            total += 10
        else:
            total += 11; aces += 1
    while total > 21 and aces:
        total -= 10; aces -= 1
    return total

def play_dealer(deck, dealer):
    while hand_value(dealer) < 17:
        dealer.append(deck.pop())

@app.post("/api/blackjack/play")
@jwt_required()
def blackjack_play():
    data = request.get_json(force=True)
    try:
        bet = Decimal(str(data.get("bet")))
    except Exception:
        return {"error": "invalid_bet"}, 400
    if bet <= 0:
        return {"error": "bet_must_be_positive"}, 400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        g = get_game(s, "blackjack")
        debit(s, u, as_money(bet))

        deck = fresh_shoe()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        # simple auto strategy: hit until 17+
        while hand_value(player) < 17:
            player.append(deck.pop())
        play_dealer(deck, dealer)

        pv, dv = hand_value(player), hand_value(dealer)

        if pv > 21:
            outcome, payout = "lose", Decimal("0")
        elif dv > 21 or pv > dv:
            if len(player) == 2 and pv == 21:
                payout = bet * Decimal("2.5")   # 3:2 (bet + 1.5x profit)
            else:
                payout = bet * Decimal("2.0")   # even money (bet + profit)
            outcome = "win"
            credit(s, u, as_money(payout))
        elif pv == dv:
            payout = bet                        # push (return stake)
            outcome = "push"
            credit(s, u, as_money(payout))
        else:
            outcome, payout = "lose", Decimal("0")

        b = Bet(
            user_id=u.id, game_id=g.id, amount=bet, outcome=outcome,
            payout=payout, result_meta={
                "player": player, "dealer": dealer,
                "player_value": pv, "dealer_value": dv
            }
        )
        s.add(b)
        s.commit()

        return {
            "ok": True,
            "outcome": outcome,
            "payout": as_money(payout),
            "balance": as_money(u.balance),
            "cards": {
                "player": player, "dealer": dealer,
                "player_value": pv, "dealer_value": dv
            }
        }
    except ValueError as e:
        s.rollback()
        return {"error": str(e)}, 400
    except Exception:
        s.rollback()
        return {"error": "server_error"}, 500
    finally:
        s.close()

# ---------------------- GAMES: SLOTS ----------------------
SLOTS_REEL = ["7","BAR","🍒","💎","🔔","⭐","🍋"]
PAYTABLE = {
    ("7","7","7"): 50,
    ("BAR","BAR","BAR"): 20,
    ("💎","💎","💎"): 10,
    ("🍒","🍒","🍒"): 8,
    ("🔔","🔔","🔔"): 6,
    ("⭐","⭐","⭐"): 4,
    ("🍋","🍋","🍋"): 3,
    "ANY_CHERRY": 2
}

def slots_symbols():
    return [random.choice(SLOTS_REEL) for _ in range(3)]

def slots_multiplier(symbols):
    tup = tuple(symbols)
    if tup in PAYTABLE: return PAYTABLE[tup]
    if symbols.count("🍒") == 2: return 3
    if symbols.count("🍒") == 1: return PAYTABLE["ANY_CHERRY"]
    return 0

@app.post("/api/slots/spin")
@jwt_required()
def slots_spin():
    data = request.get_json(force=True)
    try:
        bet = Decimal(str(data.get("bet")))
    except Exception:
        return {"error": "invalid_bet"}, 400
    if bet <= 0:
        return {"error": "bet_must_be_positive"}, 400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        g = get_game(s, "slots")
        debit(s, u, as_money(bet))

        symbols = slots_symbols()
        mult = slots_multiplier(symbols)
        payout = bet * Decimal(str(mult))
        outcome = "win" if payout > 0 else "lose"

        if payout > 0:
            credit(s, u, as_money(payout))

        b = Bet(
            user_id=u.id, game_id=g.id, amount=bet, outcome=outcome,
            payout=payout, result_meta={"symbols": symbols, "multiplier": mult}
        )
        s.add(b)
        s.commit()

        return {
            "ok": True,
            "outcome": outcome,
            "symbols": symbols,
            "multiplier": mult,
            "payout": as_money(payout),
            "balance": as_money(u.balance)
        }
    except ValueError as e:
        s.rollback()
        return {"error": str(e)}, 400
    except Exception:
        s.rollback()
        return {"error": "server_error"}, 500
    finally:
        s.close()

# ---------------------- GAMES: ROULETTE -------------------
RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
BLACK_NUMS = set(range(1,37)) - RED_NUMS

def spin_wheel():
    return random.randint(0,36)  # 0..36 (single-zero European)

@app.post("/api/roulette/bet")
@jwt_required()
def roulette_bet():
    data = request.get_json(force=True)
    color = (data.get("color") or "").lower()
    if color not in ("red","black"):
        return {"error": "color_must_be_red_or_black"}, 400
    try:
        bet = Decimal(str(data.get("bet")))
    except Exception:
        return {"error": "invalid_bet"}, 400
    if bet <= 0:
        return {"error": "bet_must_be_positive"}, 400

    s = SessionLocal()
    try:
        u = get_user(s, get_jwt_identity())
        g = get_game(s, "roulette")
        debit(s, u, as_money(bet))

        n = spin_wheel()
        won = (n in RED_NUMS and color == "red") or (n in BLACK_NUMS and color == "black")
        payout = bet * Decimal("2.0") if won else Decimal("0")
        if payout > 0:
            credit(s, u, as_money(payout))

        outcome = "win" if won else "lose"
        res_color = "green" if n == 0 else ("red" if n in RED_NUMS else "black")

        b = Bet(
            user_id=u.id, game_id=g.id, amount=bet, outcome=outcome, payout=payout,
            result_meta={"number": n, "color": res_color}
        )
        s.add(b)
        s.commit()

        return {
            "ok": True,
            "outcome": outcome,
            "roll": n,
            "roll_color": res_color,
            "payout": as_money(payout),
            "balance": as_money(u.balance)
        }
    except ValueError as e:
        s.rollback()
        return {"error": str(e)}, 400
    except Exception:
        s.rollback()
        return {"error": "server_error"}, 500
    finally:
        s.close()

# ---------------------- HEALTH ----------------------------
@app.get("/healthz")
def health():
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=True)