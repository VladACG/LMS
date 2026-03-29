from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import User

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user: User
    roles: set[str]

    @property
    def must_change_password(self) -> bool:
        return self.user.temp_password_required and 'student' in self.roles


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {'sub': user_id, 'exp': expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get('sub')
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token payload')
        return user_id
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid or expired token') from exc


def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')

    user_id = _decode_token(credentials.credentials)
    user = db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles), selectinload(User.student_link))
    ).scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')

    if user.blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User is blocked')

    roles = {role.role.value for role in user.roles}
    ctx = AuthContext(user=user, roles=roles)

    if ctx.must_change_password and request.url.path not in {'/api/auth/change-password', '/api/auth/me'}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Password change required')

    return ctx


def require_roles(*required_roles: str):
    def dependency(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if required_roles and not set(required_roles).intersection(ctx.roles):
            raise HTTPException(status_code=403, detail='Forbidden for current role')
        return ctx

    return dependency


def has_role(ctx: AuthContext, role: str) -> bool:
    return role in ctx.roles
