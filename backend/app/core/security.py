import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import AuthenticationError

# customer_*: phiên khách hàng Zalo Mini App (sub = Zalo ID), không dùng được cho API nhân viên.
TokenKind = Literal["access", "refresh", "customer_access", "customer_refresh"]

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
    subject: str  # user id (UUID) hoặc Zalo ID với token khách hàng
    company_id: uuid.UUID | None
    kind: TokenKind
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    jti: str | None = None
    via: str | None = None  # "zalo": phiên lái xe đăng nhập qua Zalo Mini App

    @property
    def user_id(self) -> uuid.UUID:
        return uuid.UUID(self.subject)


def create_token(
    subject: uuid.UUID | str,
    company_id: uuid.UUID | None,
    kind: TokenKind,
    *,
    via: str | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if kind.endswith("access")
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    claims = {
        "sub": str(subject),
        "cid": str(company_id) if company_id else None,
        "typ": kind,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    if via:
        claims["via"] = via
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
        payload = TokenPayload(
            subject=str(claims["sub"]),
            company_id=uuid.UUID(cid) if cid else None,
            kind=expected_kind,
            issued_at=datetime.fromtimestamp(claims["iat"], UTC) if "iat" in claims else None,
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
            jti=claims.get("jti"),
            via=claims.get("via"),
        )
        if not expected_kind.startswith("customer"):
            uuid.UUID(payload.subject)  # token nhân viên: sub phải là UUID
        return payload
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthenticationError("Token không hợp lệ hoặc đã hết hạn") from exc
