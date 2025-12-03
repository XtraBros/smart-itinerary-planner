import json
import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any

from werkzeug.security import generate_password_hash, check_password_hash

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "accounts.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _row_to_account(row) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "password_hash": row["password_hash"],
        "config": json.loads(row["config_json"]) if row["config_json"] else {},
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_account(username: str, password: str, config: Optional[Dict[str, Any]] = None, make_active: bool = False) -> int:
    now = datetime.utcnow().isoformat()
    config_json = json.dumps(config or {})
    password_hash = generate_password_hash(password)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO accounts (username, password_hash, config_json, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, password_hash, config_json, 1 if make_active else 0, now, now),
    )
    account_id = cursor.lastrowid
    if make_active:
        cursor.execute("UPDATE accounts SET is_active = 0 WHERE id != ?", (account_id,))
    conn.commit()
    conn.close()
    return account_id


def get_account_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_account(row)


def get_account_by_id(account_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.close()
    return _row_to_account(row)


def verify_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    account = get_account_by_username(username)
    if not account:
        return None
    if not check_password_hash(account["password_hash"], password):
        return None
    return account


def get_active_account() -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM accounts WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_account(row)


def set_active_account(account_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE accounts SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (account_id,))
    cursor.execute("UPDATE accounts SET updated_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), account_id))
    conn.commit()
    conn.close()


def get_account_config(account_id: int) -> Dict[str, Any]:
    account = get_account_by_id(account_id)
    if not account:
        return {}
    return account["config"] or {}


def update_account_config(account_id: int, config: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET config_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (json.dumps(config or {}), datetime.utcnow().isoformat(), account_id),
    )
    conn.commit()
    conn.close()


def update_account_password(account_id: int, password: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET password_hash = ?, updated_at = ?
        WHERE id = ?
        """,
        (generate_password_hash(password), datetime.utcnow().isoformat(), account_id),
    )
    conn.commit()
    conn.close()
