import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import AuthenticationError

TokenKind = Literal["access", "refresh"]

_password_hash = PasswordHash.recommended()
# Hash giả để thời gian xử lý khi sai username tương đương khi sai mật khẩu.
_DUMMY_HASH = _password_hash.hash("dummy-password")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> tuple[bool, str | None]:
    """Trả về (hợp lệ, hash mới nếu cần rehash)."""
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False, None
    return _password_hash.verify_and_update(password, password_hash)


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    company_id: uuid.UUID | None
    kind: TokenKind
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    jti: str | None = None


def create_token(user_id: uuid.UUID, company_id: uuid.UUID | None, kind: TokenKind) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if kind == "access"
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    claims = {
        "sub": str(user_id),
        "cid": str(company_id) if company_id else None,
        "typ": kind,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_kind: TokenKind) -> TokenPayload:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "typ", "exp"]},
        )
        if claims["typ"] != expected_kind:
            raise AuthenticationError("Sai loại token")
        cid = claims.get("cid")
        return TokenPayload(
            user_id=uuid.UUID(claims["sub"]),
            company_id=uuid.UUID(cid) if cid else None,
            kind=expected_kind,
            issued_at=datetime.fromtimestamp(claims["iat"], UTC) if "iat" in claims else None,
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
            jti=claims.get("jti"),
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthenticationError("Token không hợp lệ hoặc đã hết hạn") from exc
