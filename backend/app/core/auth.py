import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum

from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import LoginSession, User

load_dotenv()

PASSWORD_ITERATIONS = 600_000
SESSION_DAYS = 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(str, Enum):
    SUPPLIER = "supplier"
    PLANNER = "planner"
    CARRIER = "carrier_warehouse_operator"
    ANALYST = "logistics_analyst"
    MANAGER = "operations_manager"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded_hash.split("$")
        iterations = int(iterations_text)
        if algorithm != "pbkdf2_sha256" or iterations < 1:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_login_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=utc_now() + timedelta(days=SESSION_DAYS),
    ))
    db.commit()
    return token


def current_login_session(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> LoginSession:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please log in to continue")
    token = authorization.removeprefix("Bearer ").strip()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    login_session = db.query(LoginSession).filter(
        LoginSession.token_hash == token_hash,
        LoginSession.expires_at > utc_now(),
    ).first()
    if login_session is None:
        raise HTTPException(401, "Your session has expired. Please log in again")
    return login_session


def current_user(login_session: LoginSession = Depends(current_login_session)) -> User:
    return login_session.user


def allow(*roles: Role):
    def check(user: User = Depends(current_user)):
        try:
            user_role = Role(user.role)
        except ValueError as exc:
            raise HTTPException(403, "This account has an unsupported role") from exc
        if user_role not in roles:
            raise HTTPException(403, "Your account cannot perform this action")
        return user
    return check


def ensure_bootstrap_admin(db: Session) -> None:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip().lower()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if bool(username) != bool(password):
        raise RuntimeError("Set both BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD, or leave both empty")
    if not username:
        return
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username):
        raise RuntimeError("BOOTSTRAP_ADMIN_USERNAME must be 3 to 32 letters, numbers, dots, underscores, or hyphens")
    if len(password) < 10 or len(password) > 128:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be 10 to 128 characters")
    if db.query(User).filter(User.role == Role.MANAGER.value).first():
        return
    if db.query(User).filter(User.username == username).first():
        raise RuntimeError("Bootstrap admin username already exists with a different role")

    db.add(User(username=username, password_hash=hash_password(password), role=Role.MANAGER.value))
    db.commit()
