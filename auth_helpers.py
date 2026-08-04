"""Flask session helpers for Logbook Viso."""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from flask import jsonify, redirect, request, session, url_for

from users_store import User, can_access_toern, can_edit_photo, get_user_by_id

F = TypeVar("F", bound=Callable)


def login_user(user: User) -> None:
    session.clear()
    session["user_id"] = user.id
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_user(db_path) -> User | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return get_user_by_id(db_path, int(uid))


def require_login_api(db_path):
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user(db_path)
            if user is None:
                return jsonify({"error": "Anmeldung erforderlich."}), 401
            return fn(*args, user=user, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_admin_api(db_path):
    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user(db_path)
            if user is None:
                return jsonify({"error": "Anmeldung erforderlich."}), 401
            if user.role != "admin":
                return jsonify({"error": "Admin-Rechte erforderlich."}), 403
            return fn(*args, user=user, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_toern_access(db_path, toern_id: int, user: User):
    if not can_access_toern(user, toern_id):
        return jsonify({"error": "Kein Zugriff auf diesen Törn."}), 403
    return None


def require_photo_edit(db_path, photo_id: int, user: User):
    if not can_edit_photo(db_path, user, photo_id):
        return jsonify({"error": "Keine Berechtigung für dieses Foto."}), 403
    return None
