"""Authentication and Authorization Module for CheckMate Web.

Provides SQLite persistence, user management (Admin/User roles),
PBKDF2 password hashing, session checking, and encrypted backend config storage.
Uses Python stdlib (sqlite3, hashlib, secrets, base64) for maximum reliability and zero external C-deps.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Database path
DB_DIR = Path.home() / ".bod"
DB_PATH = DB_DIR / "bod_web.db"

# Master encryption secret from ENV or auto-generated local key file
SECRET_KEY_PATH = DB_DIR / ".secret_key"


def _get_master_key() -> bytes:
    """Retrieve or create persistent 32-byte secret key for configuration encryption."""
    env_secret = os.environ.get("CHECKMATE_SECRET_KEY")
    if env_secret:
        return hashlib.sha256(env_secret.encode("utf-8")).digest()
    
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_bytes()
    
    new_key = secrets.token_bytes(32)
    SECRET_KEY_PATH.write_bytes(new_key)
    try:
        os.chmod(SECRET_KEY_PATH, 0o600)
    except Exception:
        pass
    return new_key


def _encrypt(val: str) -> str:
    """XOR/HMAC style light encryption for stored settings at rest."""
    if not val:
        return ""
    key = _get_master_key()
    val_bytes = val.encode("utf-8")
    cipher = bytes([b ^ key[i % len(key)] for i, b in enumerate(val_bytes)])
    return base64.b64encode(cipher).decode("utf-8")


def _decrypt(val_enc: str) -> str:
    """Decrypt setting value stored in DB."""
    if not val_enc:
        return ""
    try:
        cipher = base64.b64decode(val_enc.encode("utf-8"))
        key = _get_master_key()
        plain = bytes([b ^ key[i % len(key)] for i, b in enumerate(cipher)])
        return plain.decode("utf-8")
    except Exception:
        return ""


def get_db() -> sqlite3.Connection:
    """Return SQLite connection with dictionary-like row access."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables and seed default admin user."""
    conn = get_db()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)

    # App Settings table (encrypted keys/models)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value_encrypted TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # User Audits History table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        rfp_filename TEXT NOT NULL,
        status TEXT NOT NULL,
        score REAL DEFAULT 0.0,
        report_path TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    conn.commit()

    # Seed default admin user if no admin exists
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin'")
    row = cursor.fetchone()
    if row and row["count"] == 0:
        create_user(
            username="admin",
            email="admin@checkmate.local",
            password="AdminPassword123!",
            role="admin",
        )

    conn.close()


# ── Password Utilities ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against PBKDF2 hash."""
    try:
        salt, expected_dk = stored_hash.split("$")
        actual_dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        ).hex()
        return secrets.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False


# ── User Operations ────────────────────────────────────────────────

def create_user(username: str, email: str, password: str, role: str = "user") -> Dict[str, Any]:
    """Create a new user account."""
    conn = get_db()
    cursor = conn.cursor()

    pwd_hash = hash_password(password)
    now = datetime.utcnow().isoformat()

    try:
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (username.strip(), email.strip().lower(), pwd_hash, role, now),
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return {"id": user_id, "username": username, "email": email, "role": role}
    except sqlite3.IntegrityError as e:
        conn.close()
        raise ValueError(f"User with username '{username}' or email '{email}' already exists.") from e


def authenticate_user(username_or_email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user credentials. Returns user dict if valid, else None."""
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = 1"
    cursor.execute(query, (username_or_email.strip(), username_or_email.strip().lower()))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    if verify_password(password, row["password_hash"]):
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
        }
    return None


def list_users() -> List[Dict[str, Any]]:
    """List all registered users."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, role, is_active, created_at FROM users ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id: int) -> bool:
    """Delete a user account by ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


def update_user_password(user_id: int, new_password: str) -> bool:
    """Update user password."""
    conn = get_db()
    cursor = conn.cursor()
    pwd_hash = hash_password(new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    return rows_affected > 0


# ── System Settings Operations (Encrypted at Rest) ──────────────────

def get_setting(key: str, default: str = "") -> str:
    """Get decrypted setting value from database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value_encrypted FROM app_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return default
    decrypted = _decrypt(row["value_encrypted"])
    return decrypted if decrypted else default


def set_setting(key: str, value: str) -> None:
    """Set and encrypt setting value in database."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    enc_val = _encrypt(value)

    cursor.execute("""
    INSERT INTO app_settings (key, value_encrypted, updated_at)
    VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET
        value_encrypted = excluded.value_encrypted,
        updated_at = excluded.updated_at
    """, (key, enc_val, now))

    conn.commit()
    conn.close()


# ── Audit History Operations ────────────────────────────────────────

def record_audit_run(user_id: int, username: str, rfp_filename: str, status: str, score: float = 0.0, report_path: str = "") -> int:
    """Record an audit execution run."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO audit_runs (user_id, username, rfp_filename, status, score, report_path, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, rfp_filename, status, score, report_path, now))
    conn.commit()
    run_id = cursor.lastrowid
    conn.close()
    return run_id


def list_audit_runs(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List audit runs (filtered by user_id if provided)."""
    conn = get_db()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT * FROM audit_runs WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
    else:
        cursor.execute("SELECT * FROM audit_runs ORDER BY id DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Initialize DB on module import
init_db()
