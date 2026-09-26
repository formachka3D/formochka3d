"""Account persistence for Formochka3D. No web routes or SMTP side effects."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}$")
PBKDF2_ITERATIONS = 600_000


def normalize_email(email: str) -> str:
    result = email.strip().casefold()
    if len(result) > 254 or not EMAIL_RE.fullmatch(result):
        raise ValueError("Неверный адрес электронной почты")
    return result


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError("Пароль должен содержать от 12 до 128 символов")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, dklen=32)
    return "pbkdf2_sha256$600000$" + salt.hex() + "$" + derived.hex()


def check_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$")
        if (algorithm, iterations) != ("pbkdf2_sha256", "600000"):
            return False
        derived = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS, dklen=32)
        return hmac.compare_digest(derived, bytes.fromhex(digest))
    except (ValueError, TypeError, UnicodeError):
        return False


class AccountStore:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, mode=0o700, exist_ok=True)
        self.init_schema()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    def init_schema(self):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user'
                        CHECK(role IN ('user', 'admin')),
                    verified_at INTEGER,
                    disabled_at INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS one_time_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    purpose TEXT NOT NULL CHECK(purpose IN ('verify', 'reset')),
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_tokens_user ON one_time_tokens(user_id);
                CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
            """)

    def register(self, email: str, password: str) -> int:
        email = normalize_email(email)
        password_hash = hash_password(password)
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO users(email,password_hash,created_at) VALUES (?,?,?)",
                (email, password_hash, int(time.time())))
            return cursor.lastrowid

    def find_user(self, email: str):
        with self.connect() as db:
            row = db.execute("SELECT id,email,role,verified_at,disabled_at FROM users WHERE email=?",
                             (normalize_email(email),)).fetchone()
            return dict(row) if row else None

    def authenticate(self, email: str, password: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE email=?", (normalize_email(email),)).fetchone()
        if row is None or not check_password(password, row["password_hash"]):
            return None
        if row["verified_at"] is None or row["disabled_at"] is not None:
            return None
        return {"id": row["id"], "email": row["email"], "role": row["role"]}

    def issue_one_time(self, user_id: int, purpose: str, ttl: int) -> str:
        if purpose not in ("verify", "reset") or not 60 <= ttl <= 86400:
            raise ValueError("Неверное назначение или срок действия")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            db.execute("DELETE FROM one_time_tokens WHERE user_id=? AND purpose=?", (user_id, purpose))
            db.execute("INSERT INTO one_time_tokens VALUES (?,?,?,?)",
                       (digest, user_id, purpose, int(time.time()) + ttl))
        return token

    def consume_one_time(self, token: str, purpose: str, new_password: str | None = None) -> bool:
        if purpose not in ("verify", "reset") or len(token) > 256:
            return False
        password_hash = hash_password(new_password) if purpose == "reset" and new_password is not None else None
        if purpose == "reset" and password_hash is None:
            return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = int(time.time())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record = db.execute(
                "SELECT user_id FROM one_time_tokens WHERE token_hash=? AND purpose=? AND expires_at>?",
                (digest, purpose, now)).fetchone()
            if record is None:
                return False
            user_id = record["user_id"]
            if purpose == "verify":
                db.execute("UPDATE users SET verified_at=? WHERE id=? AND disabled_at IS NULL", (now, user_id))
            else:
                db.execute("UPDATE users SET password_hash=? WHERE id=? AND disabled_at IS NULL",
                           (password_hash, user_id))
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM one_time_tokens WHERE token_hash=?", (digest,))
            return True

    def create_session(self, user_id: int, ttl: int = 14 * 86400) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                       (hashlib.sha256(token.encode()).hexdigest(), user_id,
                        int(time.time()) + ttl, int(time.time())))
        return token

    def get_session(self, token: str):
        if len(token) > 256:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("""
                SELECT u.id,u.email,u.role FROM sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>? AND u.disabled_at IS NULL
                      AND u.verified_at IS NOT NULL
            """, (digest, int(time.time()))).fetchone()
            return dict(row) if row else None

    def logout(self, token: str):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?",
                       (hashlib.sha256(token.encode()).hexdigest(),))

    def set_disabled(self, user_id: int, disabled: bool):
        with self.connect() as db:
            db.execute("UPDATE users SET disabled_at=? WHERE id=? AND role='user'",
                       (int(time.time()) if disabled else None, user_id))
            if disabled:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
