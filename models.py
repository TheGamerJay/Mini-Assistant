from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import re, datetime as dt

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    pw_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    def set_password(self, raw):
        self.pw_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.pw_hash, raw)

def password_valid(pw: str) -> bool:
    if len(pw) < 8: return False
    if not re.search(r"[A-Za-z]", pw): return False
    if not re.search(r"\d", pw): return False
    return True