from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import authenticate, create_token, current_user, limiter
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


def _client(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "unknown")


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    client = _client(request)
    wait = limiter.blocked(client, body.username)
    if wait:
        raise HTTPException(429, "too many failed logins, try again later", headers={"Retry-After": str(wait)})

    user = authenticate(db, body.username, body.password)
    if user is None:
        limiter.failed(client, body.username)
        raise HTTPException(401, "wrong username or password")

    limiter.succeeded(client, body.username)
    token, expires = create_token(user)
    return TokenOut(access_token=token, expires_in=expires, role=user.role)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}
