"""Users, Törn-Zuordnung und Auth (gespeichert in SYSTEM_DB / system.sqlite)."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

ROLE_ADMIN = "admin"
ROLE_USER = "user"


@dataclass
class User:
    id: int
    username: str
    role: str
    toern_ids: list[int]


def init_app_db(db_path) -> None:
    from pathlib import Path

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_toerns (
                user_id INTEGER NOT NULL,
                toern_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, toern_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_toerns_user ON user_toerns(user_id)"
        )


def get_conn(db_path) -> sqlite3.Connection:
    init_app_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_bootstrap_admin(
    db_path,
    username: str | None,
    password: str | None,
) -> None:
    if not username or not password:
        return
    with get_conn(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n > 0:
            return
        now = int(time.time() * 1000)
        conn.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at_ms)
            VALUES (?, ?, ?, ?)
            """,
            (username.strip(), generate_password_hash(password), ROLE_ADMIN, now),
        )
        conn.commit()


def authenticate(db_path, username: str, password: str) -> User | None:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return None
        toerns = _toerns_for_user(conn, int(row["id"]))
        return User(
            id=int(row["id"]),
            username=row["username"],
            role=row["role"],
            toern_ids=toerns,
        )


def get_user_by_id(db_path, user_id: int) -> User | None:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return User(
            id=int(row["id"]),
            username=row["username"],
            role=row["role"],
            toern_ids=_toerns_for_user(conn, user_id),
        )


def _toerns_for_user(conn: sqlite3.Connection, user_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT toern_id FROM user_toerns WHERE user_id = ? ORDER BY toern_id",
        (user_id,),
    ).fetchall()
    return [int(r["toern_id"]) for r in rows]


def user_to_public_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "toernIds": user.toern_ids,
        "isAdmin": user.role == ROLE_ADMIN,
    }


def can_access_toern(user: User, toern_id: int) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    return toern_id in user.toern_ids


def get_photo_owner_id(db_path, photo_id: int) -> int | None:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT uploaded_by_user_id FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
        if row is None:
            return None
        val = row["uploaded_by_user_id"]
        return int(val) if val is not None else None


def can_edit_photo(db_path, user: User, photo_id: int) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    owner = get_photo_owner_id(db_path, photo_id)
    if owner is None:
        return False
    return owner == user.id


def list_users(db_path) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at_ms FROM users ORDER BY username"
        ).fetchall()
        out = []
        for r in rows:
            uid = int(r["id"])
            out.append(
                {
                    "id": uid,
                    "username": r["username"],
                    "role": r["role"],
                    "createdAtMs": r["created_at_ms"],
                    "toernIds": _toerns_for_user(conn, uid),
                }
            )
        return out


def create_user(
    db_path,
    username: str,
    password: str,
    role: str = ROLE_USER,
    toern_ids: list[int] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    username = username.strip()
    if not username or not password:
        return None, "Benutzername und Passwort erforderlich."
    if role not in (ROLE_ADMIN, ROLE_USER):
        return None, "Ungültige Rolle."
    now = int(time.time() * 1000)
    try:
        with get_conn(db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (username, generate_password_hash(password), role, now),
            )
            uid = int(cur.lastrowid)
            for tid in toern_ids or []:
                conn.execute(
                    "INSERT OR IGNORE INTO user_toerns (user_id, toern_id) VALUES (?, ?)",
                    (uid, int(tid)),
                )
            conn.commit()
        user = get_user_by_id(db_path, uid)
        return user_to_public_dict(user), None  # type: ignore[arg-type]
    except sqlite3.IntegrityError:
        return None, "Benutzername bereits vergeben."


def update_user(
    db_path,
    user_id: int,
    *,
    password: str | None = None,
    role: str | None = None,
    toern_ids: list[int] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None, "Benutzer nicht gefunden."
        if password:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(password), user_id),
            )
        if role is not None:
            if role not in (ROLE_ADMIN, ROLE_USER):
                return None, "Ungültige Rolle."
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if toern_ids is not None:
            conn.execute("DELETE FROM user_toerns WHERE user_id = ?", (user_id,))
            for tid in toern_ids:
                conn.execute(
                    "INSERT INTO user_toerns (user_id, toern_id) VALUES (?, ?)",
                    (user_id, int(tid)),
                )
        conn.commit()
    user = get_user_by_id(db_path, user_id)
    return user_to_public_dict(user), None  # type: ignore[arg-type]


def delete_user(db_path, user_id: int) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0


def username_for_id(db_path, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT username FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["username"] if row else None
