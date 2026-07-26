"""
Auth: JWT issuance/verification, password hashing, current-user + RBAC deps.

Provider-agnostic: password and SSO users share the same User row; SSO callbacks
(Google/Microsoft) mint the same JWT. The token carries the active org + role so
the DB layer can set the RLS GUC and routers can enforce the PRD role matrix.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def set_auth_cookie(response: Response, token: str) -> None:
    """Store the session JWT in an httpOnly cookie — unreadable by JS, so an XSS
    can't exfiltrate it. SameSite=Lax + non-GET mutations gives CSRF protection."""
    s = get_settings()
    response.set_cookie(
        key=s.auth_cookie_name, value=token, httponly=True,
        secure=s.auth_cookie_secure, samesite="lax", path="/",
        max_age=s.access_token_ttl_minutes * 60,
    )


def clear_auth_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        key=s.auth_cookie_name, path="/", httponly=True,
        secure=s.auth_cookie_secure, samesite="lax",
    )


def hash_password(p: str) -> str:
    # bcrypt caps input at 72 bytes; truncate defensively (longer adds no entropy).
    return bcrypt.hashpw(p.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(p: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode()[:72], hashed.encode())
    except ValueError:
        return False


class Principal(BaseModel):
    user_id: str
    organization_id: str
    role: str  # compliance_admin | head | preparer
    email: str | None = None


def create_access_token(principal: Principal) -> str:
    s = get_settings()
    payload = {
        "sub": principal.user_id, "org": principal.organization_id,
        "role": principal.role, "email": principal.email,
        "exp": datetime.now(UTC) + timedelta(minutes=s.access_token_ttl_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_invite_token(*, membership_id: str, organization_id: str, email: str,
                        ttl_days: int = 7) -> str:
    """Signed, time-limited invite token. Carries the membership it activates."""
    s = get_settings()
    payload = {
        "purpose": "invite", "mid": membership_id, "org": organization_id, "email": email,
        "exp": datetime.now(UTC) + timedelta(days=ttl_days),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_invite_token(token: str) -> dict:
    s = get_settings()
    try:
        claims = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired invite") from e
    if claims.get("purpose") != "invite":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not an invite token")
    return claims


def get_current_principal(
    request: Request,
    bearer: Annotated[str | None, Depends(oauth2_scheme)],
) -> Principal:
    s = get_settings()
    # Browser SPA -> httpOnly cookie; API clients -> Authorization: Bearer. An
    # explicit header wins over an ambient cookie (the caller is being explicit).
    token = bearer or request.cookies.get(s.auth_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from e
    return Principal(user_id=claims["sub"], organization_id=claims["org"],
                     role=claims["role"], email=claims.get("email"))


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_role(*roles: str):
    """Dependency factory enforcing the PRD role matrix on a route."""
    def _dep(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Requires role in {roles}; you are '{principal.role}'.")
        return principal
    return _dep
