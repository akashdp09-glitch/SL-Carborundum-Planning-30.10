"""Factory demo logins. Created only when that username is not already in the database.

If an older sl_planning.db was restored, the password stored there is used.
Changed passwords cannot be read back; only a hash is kept.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from pathlib import Path

DEMO_USERS = (
    ("admin", "admin123", "admin", "Administrator"),
    ("planning", "planning123", "planning", "Planning"),
    ("supervisor", "supervisor123", "supervisor", "Production Supervisor"),
    ("operator", "operator123", "operator", "Production Operator"),
    ("management", "management123", "management", "Management"),
)

USER_DETAILS_FILE = "user details.txt"


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180_000)
    return f"pbkdf2_sha256$180000${salt.hex()}${dk.hex()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        _algo, iterations, salt_hex, digest_hex = encoded.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return secrets.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def find_user(db_path, username: str):
    """Return the users-row dict (any case) or None. Does not check the password."""
    name = (username or "").strip()
    if not name:
        return None
    path = Path(db_path)
    if not path.exists():
        return None
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        r = con.execute(
            "SELECT username,password_hash,role,display_name,active FROM users WHERE lower(username)=lower(?) LIMIT 1",
            (name,),
        ).fetchone()
        return dict(r) if r else None
    except Exception:
        return None
    finally:
        con.close()


def demo_secret(username: str) -> str | None:
    key = (username or "").strip().lower()
    for name, password, _role, _display in DEMO_USERS:
        if name.lower() == key:
            return password
    return None


def reset_demo_password(db_path, username: str) -> bool:
    """Put a demo username back to the factory default password. Other users are not touched."""
    secret = demo_secret(username)
    if not secret:
        return False
    seed_users(db_path)
    row = find_user(db_path, username)
    if not row:
        return False
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "UPDATE users SET password_hash=?, active=1 WHERE lower(username)=lower(?)",
            (hash_password(secret), row["username"]),
        )
        con.commit()
        return True
    finally:
        con.close()


def explain_login_failure(db_path, username: str, password: str) -> str:
    name = (username or "").strip() or "(empty)"
    path = Path(db_path)
    row = find_user(db_path, name)
    secret = demo_secret(name)
    if not path.exists():
        return f"No user database yet at {path}."
    if row is None:
        return f"Username {name!r} is not in {path}."
    if not row.get("active", 1):
        return f"Username {row['username']!r} exists in {path} but is inactive."
    if secret and password == secret:
        return (
            f"Username {row['username']!r} is in {path}, but the saved password is not the demo password. "
            f"This database came from an earlier install. Open {USER_DETAILS_FILE} in the program folder."
        )
    if secret:
        return (
            f"Username {row['username']!r} is in {path}. "
            f"The saved password is not the new-unzip password in {USER_DETAILS_FILE}."
        )
    return f"Username {row['username']!r} is in {path}. The password did not match."


def seed_users(db_path) -> int:
    """Create the users table if needed and add missing demo usernames. Never overwrite an existing hash."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                display_name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        added = 0
        for username, password, role, display in DEMO_USERS:
            if con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone() is None:
                con.execute(
                    "INSERT INTO users(username,password_hash,role,display_name,active,created_at) VALUES(?,?,?,?,1,CURRENT_TIMESTAMP)",
                    (username, hash_password(password), role, display),
                )
                added += 1
        con.commit()
        return added
    finally:
        con.close()
