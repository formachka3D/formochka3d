"""Run with python3 tests/test_account_store.py; no web or email provider needed."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web.account_store import AccountStore


def run():
    with tempfile.TemporaryDirectory() as tmp:
        store = AccountStore(os.path.join(tmp, "users.sqlite3"))
        user_id = store.register(" User@Example.com ", "Long!safe!password2026")
        record = store.find_user("user@example.com")
        assert record["id"] == user_id and record["role"] == "user"
        assert store.authenticate("user@example.com", "Long!safe!password2026") is None
        try:
            store.register("user@example.com", "AnotherSafePassword22")
            raise AssertionError("Duplicate email was accepted")
        except sqlite3.IntegrityError:
            pass

        verify = store.issue_one_time(user_id, "verify", 3600)
        with store.connect() as db:
            raw = str(db.execute("SELECT token_hash FROM one_time_tokens").fetchone()[0])
            password_hash = str(db.execute("SELECT password_hash FROM users").fetchone()[0])
        assert verify not in raw
        assert "Long!safe!password2026" not in password_hash
        assert store.consume_one_time("fake", "verify") is False
        assert store.consume_one_time(verify, "verify") is True
        assert store.consume_one_time(verify, "verify") is False
        user = store.authenticate("user@example.com", "Long!safe!password2026")
        assert user["id"] == user_id

        session = store.create_session(user_id)
        assert store.get_session(session)["role"] == "user"
        reset = store.issue_one_time(user_id, "reset", 600)
        assert store.consume_one_time(reset, "reset", "AnotherVerySecurePassword2026")
        assert store.get_session(session) is None
        assert store.authenticate("user@example.com", "Long!safe!password2026") is None
        assert store.authenticate("user@example.com", "AnotherVerySecurePassword2026")
        new_session = store.create_session(user_id)
        store.set_disabled(user_id, True)
        assert store.get_session(new_session) is None
        assert store.authenticate("user@example.com", "AnotherVerySecurePassword2026") is None
        store.set_disabled(user_id, False)
        assert store.authenticate("user@example.com", "AnotherVerySecurePassword2026")
        print("PASS: registration, uniqueness, verification, login, sessions, reset, blocking")


if __name__ == "__main__":
    run()
