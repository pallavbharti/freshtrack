import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

log = logging.getLogger(__name__)

ROLES = ("viewer", "manager")
ALGORITHM = "HS256"
_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

_DUMMY_HASH = _hasher.hash("not-a-real-password")


def _jwt_secret() -> str:
    if settings.jwt_secret:
        return settings.jwt_secret
    if settings.app_env == "production":
        raise RuntimeError("JWT_SECRET must be set in production")
    settings.jwt_secret = secrets.token_urlsafe(48)
    log.warning("JWT_SECRET not set - using a random secret for this process (dev only)")
    return settings.jwt_secret


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def create_token(user: User) -> tuple[str, int]:
    expires = settings.jwt_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {"sub": user.username, "role": user.role, "iat": now, "exp": now + timedelta(seconds=expires)}
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM), expires


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        verify_password(_DUMMY_HASH, password)
        return None
    return user if verify_password(user.password_hash, password) else None


class LoginLimiter:
    def __init__(self):
        self._fails: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key, now):
        q = self._fails[key]
        while q and now - q[0] > settings.login_window_seconds:
            q.popleft()
        return q

    def blocked(self, client: str, username: str) -> int:
        now = time.monotonic()
        with self._lock:
            q = self._recent((client, username.lower()), now)
            if len(q) >= settings.login_max_failures:
                return int(settings.login_window_seconds - (now - q[0])) + 1
        return 0

    def failed(self, client: str, username: str):
        with self._lock:
            self._fails[(client, username.lower())].append(time.monotonic())

    def succeeded(self, client: str, username: str):
        with self._lock:
            self._fails.pop((client, username.lower()), None)

    def reset(self):
        with self._lock:
            self._fails.clear()


limiter = LoginLimiter()


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated",
                                 headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, _jwt_secret(), algorithms=[ALGORITHM],
                             options={"require": ["exp", "sub", "role"]})
    except jwt.PyJWTError as err:
        raise unauthorized from err
    user = db.scalar(select(User).where(User.username == payload["sub"]))
    if user is None:
        raise unauthorized
    return user


def require_viewer(user: User = Depends(current_user)) -> User:
    return user


def require_manager(user: User = Depends(current_user)) -> User:
    if user.role != "manager":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "manager role required")
    return user


def ensure_initial_users(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(User)):
        return
    for username, password, role in (("manager", settings.initial_manager_password, "manager"),
                                     ("viewer", settings.initial_viewer_password, "viewer")):
        if not password:
            if settings.app_env == "production":
                raise RuntimeError(f"INITIAL_{role.upper()}_PASSWORD must be set in production")
            password = f"{role}-dev-password"
            log.warning("no INITIAL_%s_PASSWORD - created '%s' with the dev password (dev only)",
                        role.upper(), username)
        db.add(User(username=username, password_hash=hash_password(password), role=role))
    db.commit()
