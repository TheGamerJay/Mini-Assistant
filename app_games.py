import os, random
from dataclasses import dataclass
from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Numeric, Boolean, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError

# ---------- DB setup ----------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

# ---------- Models (match schema you created) ----------
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
    outcome = Column(String(20))           # win / lose / push
    payout = Column(Numeric(12,2), default=0)
    result_meta = Column(JSON)             # json details (cards, reels, number)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

# Ensure games catalog exists (idempotent)
def ensure_games():
    session = SessionLocal()
    try:
        cat = [
            ("Blackjack", "blackjack"),
            ("Roulette Red/Black", "roulette"),
            ("Slots – Chips Only", "slots"),
        ]
        for name, gtype in cat:
            if not session.query(Game).filter_by(name=name).first():
                session.add(Game(name=name, type=gtype))
        session.commit()
    finally:
        session.close()

ensure_games()

# ---------- Helpers ----------
def get_or_400(d, key, cast=float):
    if key not in d:
        raise ValueError(f"Missing field: {key}")
    try:
        return cast(d[key])
    except Exception:
        raise ValueError(f"Invalid value for {key}")

def load_user(session, user_id:int) -> User:
    u = session.get(User, user_id)
    if not u or not u.is_active:
        raise ValueError("User not found or inactive")
    return u

def load_game(session, gtype:str) -> Game:
    g = session.query(Game).filter_by(type=gtype, is_active=True).first()
    if not g:
        raise ValueError(f"Game type not active: {gtype}")
    return g

def debit(session, user:User, amt:float):
    if float(user.balance) < amt:
        raise ValueError("Insufficient balance")
    user.balance = float(user.balance) - amt
    session.flush()

def credit(session, user:User, amt:float):
    user.balance = float(user.balance) + amt
    session.flush()

# ---------- Blackjack Core ----------
RANKS = list(range(2, 11)) + ['J','Q','K','A']
SUITS = ['♠','♥','♦','♣']

def fresh_shoe():
    deck = [(r,s) for r in RANKS for s in SUITS] * 6
    random.shuffle(deck)
    return deck

def hand_value(cards):
    # count Aces as 11 then drop to 1 as needed
    total, aces = 0, 0
    for r,_ in cards:
        if isinstance(r, int):
            total += r
        elif r in ['J','Q','K']:
            total += 10
        else:  # Ace
            total += 11
            aces += 1
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def play_dealer(deck, dealer):
    while hand_value(dealer) < 17:
        dealer.append(deck.pop())

# ---------- Slots Core ----------
SLOTS_REEL = ["7","BAR","🍒","💎","🔔","⭐","🍋"]
PAYTABLE = {
    ("7","7","7"): 50,
    ("BAR","BAR","BAR"): 20,
    ("💎","💎","💎"): 10,
    ("🍒","🍒","🍒"): 8,
    ("🔔","🔔","🔔"): 6,
    ("⭐","⭐","⭐"): 4,
    ("🍋","🍋","🍋"): 3,
    # Mixed cherries pay small
    "ANY_CHERRY": 2
}

def spin_reels():
    return [random.choice(SLOTS_REEL) for _ in range(3)]

def slots_multiplier(symbols):
    tup = tuple(symbols)
    if tup in PAYTABLE: return PAYTABLE[tup]
    if symbols.count("🍒") == 2: return 3
    if symbols.count("🍒") == 1: return PAYTABLE["ANY_CHERRY"]
    return 0

# ---------- Roulette Core ----------
RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
BLACK_NUMS = set(range(1,37)) - RED_NUMS
def spin_wheel():
    # single-zero European style (0–36)
    return random.randint(0,36)

# ---------- Blueprint ----------
casino = Blueprint("casino", __name__, url_prefix="/api")

@casino.post("/blackjack/play")
def blackjack_play():
    """
    JSON: { "user_id": 1, "bet": 10 }
    Returns: balances + cards + outcome + payout
    """
    data = request.get_json(force=True)
    try:
        user_id = get_or_400(data, "user_id", int)
        bet = get_or_400(data, "bet", float)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    session = SessionLocal()
    try:
        user = load_user(session, user_id)
        game = load_game(session, "blackjack")
        debit(session, user, bet)

        deck = fresh_shoe()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        # auto-stand strategy: hit until 17+
        while hand_value(player) < 17:
            player.append(deck.pop())

        play_dealer(deck, dealer)

        pv, dv = hand_value(player), hand_value(dealer)

        if pv > 21:
            outcome, payout = "lose", 0
        elif dv > 21 or pv > dv:
            # Natural blackjack pays 3:2
            if len(player) == 2 and hand_value(player) == 21:
                payout = bet * 2.5  # returns bet + profit(1.5x)
            else:
                payout = bet * 2.0  # even-money win (bet + profit)
            outcome = "win"
            credit(session, user, payout)
        elif pv == dv:
            payout = bet        # push, return stake
            outcome = "push"
            credit(session, user, payout)
        else:
            outcome, payout = "lose", 0

        b = Bet(
            user_id=user.id,
            game_id=game.id,
            amount=bet,
            outcome=outcome,
            payout=payout,
            result_meta={
                "player": player,
                "dealer": dealer,
                "player_value": pv,
                "dealer_value": dv
            }
        )
        session.add(b)
        session.commit()

        return jsonify({
            "ok": True,
            "outcome": outcome,
            "payout": float(payout),
            "balance": float(user.balance),
            "cards": {
                "player": player, "dealer": dealer,
                "player_value": pv, "dealer_value": dv
            }
        })
    except ValueError as e:
        session.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        session.rollback()
        return jsonify({"error": "server_error"}), 500
    finally:
        session.close()

@casino.post("/roulette/bet")
def roulette_bet():
    """
    JSON: { "user_id": 1, "bet": 10, "color": "red" }  # color: red|black
    Payout: 1:1 (even money). 0 is house.
    """
    data = request.get_json(force=True)
    try:
        user_id = get_or_400(data, "user_id", int)
        bet = get_or_400(data, "bet", float)
        color = data.get("color", "").lower()
        if color not in ("red","black"):
            raise ValueError("color must be 'red' or 'black'")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    session = SessionLocal()
    try:
        user = load_user(session, user_id)
        game = load_game(session, "roulette")
        debit(session, user, bet)

        n = spin_wheel()
        won = (n in RED_NUMS and color == "red") or (n in BLACK_NUMS and color == "black")

        payout = bet * 2.0 if won else 0.0
        outcome = "win" if won else "lose"

        if payout:
            credit(session, user, payout)

        b = Bet(
            user_id=user.id, game_id=game.id, amount=bet,
            outcome=outcome, payout=payout,
            result_meta={"number": n, "color": "red" if n in RED_NUMS else ("black" if n in BLACK_NUMS else "green")}
        )
        session.add(b)
        session.commit()

        return jsonify({
            "ok": True,
            "outcome": outcome,
            "roll": n,
            "payout": float(payout),
            "balance": float(user.balance)
        })
    except ValueError as e:
        session.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception:
        session.rollback()
        return jsonify({"error": "server_error"}), 500
    finally:
        session.close()

@casino.post("/slots/spin")
def slots_spin():
    """
    JSON: { "user_id": 1, "bet": 1 }
    3-reel slot; returns symbols and payout. Chips only = amount units.
    """
    data = request.get_json(force=True)
    try:
        user_id = get_or_400(data, "user_id", int)
        bet = get_or_400(data, "bet", float)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    session = SessionLocal()
    try:
        user = load_user(session, user_id)
        game = load_game(session, "slots")
        debit(session, user, bet)

        symbols = spin_reels()
        mult = slots_multiplier(symbols)
        payout = bet * mult
        outcome = "win" if payout > 0 else "lose"

        if payout > 0:
            credit(session, user, payout)

        b = Bet(
            user_id=user.id, game_id=game.id, amount=bet,
            outcome=outcome, payout=payout,
            result_meta={"symbols": symbols, "multiplier": mult}
        )
        session.add(b)
        session.commit()

        return jsonify({
            "ok": True,
            "outcome": outcome,
            "symbols": symbols,
            "multiplier": mult,
            "payout": float(payout),
            "balance": float(user.balance)
        })
    except ValueError as e:
        session.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception:
        session.rollback()
        return jsonify({"error": "server_error"}), 500
    finally:
        session.close()

@casino.get("/users/<int:user_id>/balance")
def user_balance(user_id):
    session = SessionLocal()
    try:
        user = session.get(User, user_id)
        if not user:
            return {"error": "user_not_found"}, 404
        return {"balance": float(user.balance)}
    finally:
        session.close()