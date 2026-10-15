from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import User, session_scope


password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    return password_hash.verify(value, hashed)


def make_token(user: User) -> str:
    cfg = settings()
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "role": user.role, "iat": now,
                       "exp": now + timedelta(hours=cfg.token_hours)}, cfg.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Недействительная или просроченная сессия") from exc


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(session_scope)) -> User:
    if not credentials:
        raise HTTPException(401, "Требуется вход")
    payload = decode_token(credentials.credentials)
    user = db.scalar(select(User).where(User.id == int(payload["sub"])))
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    return user


def publisher(user: User = Depends(current_user)) -> User:
    if user.role not in {"publisher", "admin"}:
        raise HTTPException(403, "Публикация доступна издателю или администратору")
    return user


def sync_access(x_sync_token: str = Header(default="")) -> None:
    if not x_sync_token or x_sync_token != settings().sync_token:
        raise HTTPException(401, "Неверный токен синхронизации")

