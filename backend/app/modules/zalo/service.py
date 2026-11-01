"""Liên kết Zalo Mini App với liên hệ khách hàng / tài xế bằng mã kích hoạt (D32)."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import throttle
from app.core.config import get_settings
from app.core.db import set_tenant_context
from app.core.errors import AppError
from app.modules.audit import service as audit
from app.modules.identity import service as identity_service
from app.modules.identity.models import CompanyRole
from app.modules.master_data import service as master_data
from app.modules.master_data.models import CustomerContact
from app.modules.tenancy import service as tenancy
from app.modules.zalo.models import ActivationCode, ZaloLink
from app.modules.zalo.schemas import ActivationCodeOut, ZaloLinkInfo, ZaloStatus, ZaloTarget

# Bỏ ký tự dễ nhầm (0/O, 1/I/L) → 31^8 ≈ 8,5·10^11 tổ hợp.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


def normalize_code(raw: str) -> str:
    return "".join(c for c in raw.upper() if c.isalnum())


def hash_code(code: str) -> str:
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def _format(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def _entity(target: ZaloTarget) -> tuple[str, uuid.UUID]:
    if target.contact_id is not None:
        return "customer_contact", target.contact_id
    assert target.user_id is not None
    return "user", target.user_id


def _of_target(model: type[ActivationCode] | type[ZaloLink], target: ZaloTarget):  # type: ignore[no-untyped-def]
    if target.contact_id is not None:
        return model.contact_id == target.contact_id
    return model.user_id == target.user_id


async def contact_target(
    session: AsyncSession, customer_id: uuid.UUID, contact_id: uuid.UUID
) -> ZaloTarget:
    contact = await master_data.get_contact(session, customer_id, contact_id)
    if not contact.is_active:
        raise AppError("Liên hệ đang ngưng hoạt động", code="contact_inactive")
    return ZaloTarget(contact_id=contact.id)


async def driver_target(
    session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID
) -> ZaloTarget:
    user, roles = await identity_service.get_company_user(session, company_id, user_id)
    if CompanyRole.DRIVER not in roles:
        raise AppError("Chỉ cấp mã kích hoạt Zalo cho tài khoản lái xe", code="not_driver")
    if not user.is_active:
        raise AppError("Tài khoản đang bị khóa", code="user_inactive")
    return ZaloTarget(user_id=user.id)


async def _revoke_pending_codes(session: AsyncSession, target: ZaloTarget, now: datetime) -> None:
    await session.execute(
        update(ActivationCode)
        .where(
            _of_target(ActivationCode, target),
            ActivationCode.used_at.is_(None),
            ActivationCode.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


async def issue_code(
    session: AsyncSession, company_id: uuid.UUID, target: ZaloTarget, actor_id: uuid.UUID
) -> ActivationCodeOut:
    """Cấp mã mới (mã cũ chưa dùng mất hiệu lực). Liên kết đang có giữ nguyên tới khi dùng mã."""
    now = datetime.now(UTC)
    ttl = (await tenancy.get_settings(session, company_id)).activation_code_ttl_days
    await _revoke_pending_codes(session, target, now)
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    expires_at = now + timedelta(days=ttl)
    session.add(
        ActivationCode(
            company_id=company_id,
            contact_id=target.contact_id,
            user_id=target.user_id,
            code_hash=hash_code(code),
            expires_at=expires_at,
            created_by=actor_id,
        )
    )
    entity, entity_id = _entity(target)
    audit.record(
        session,
        company_id,
        entity,
        entity_id,
        "zalo_code_issued",
        actor_id,
        expires_at=expires_at.isoformat(),
    )
    await session.flush()
    template = get_settings().zalo_activation_url
    return ActivationCodeOut(
        code=_format(code),
        expires_at=expires_at,
        link=template.format(code=code) if template else None,
    )


async def revoke(
    session: AsyncSession, company_id: uuid.UUID, target: ZaloTarget, actor_id: uuid.UUID
) -> None:
    """Thu hồi liên kết Zalo đang có và mã chưa dùng của đích."""
    now = datetime.now(UTC)
    await _revoke_pending_codes(session, target, now)
    await session.execute(
        update(ZaloLink)
        .where(_of_target(ZaloLink, target), ZaloLink.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    entity, entity_id = _entity(target)
    audit.record(session, company_id, entity, entity_id, "zalo_revoked", actor_id)
    await session.flush()


async def link_info(
    session: AsyncSession,
    *,
    contact_ids: list[uuid.UUID] | None = None,
    user_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, ZaloLinkInfo]:
    """Trạng thái Zalo theo liên hệ / tài xế (trong công ty hiện tại, nhờ RLS)."""
    contact_ids, user_ids = contact_ids or [], user_ids or []
    info: dict[uuid.UUID, ZaloLinkInfo] = {i: ZaloLinkInfo() for i in [*contact_ids, *user_ids]}
    if not info:
        return info
    now = datetime.now(UTC)
    codes = await session.scalars(
        select(ActivationCode).where(
            or_(ActivationCode.contact_id.in_(contact_ids), ActivationCode.user_id.in_(user_ids)),
            ActivationCode.used_at.is_(None),
            ActivationCode.revoked_at.is_(None),
            ActivationCode.expires_at > now,
        )
    )
    for code in codes:
        key = code.contact_id or code.user_id
        assert key is not None
        info[key].status = ZaloStatus.PENDING
        info[key].code_expires_at = code.expires_at
    links = await session.scalars(
        select(ZaloLink).where(
            or_(ZaloLink.contact_id.in_(contact_ids), ZaloLink.user_id.in_(user_ids)),
            ZaloLink.revoked_at.is_(None),
        )
    )
    for link in links:
        key = link.contact_id or link.user_id
        assert key is not None
        # Đang có liên kết mà admin cấp mã mới (đổi điện thoại) → vẫn hiện ACTIVE kèm hạn mã chờ.
        info[key].status = ZaloStatus.ACTIVE
        info[key].display_name = link.display_name
        info[key].activated_at = link.activated_at
    return info


async def redeem(
    session: AsyncSession,
    raw_code: str,
    *,
    zalo_user_id: str,
    display_name: str | None,
    ip: str | None,
) -> ZaloLink:
    """Nhập mã trên Zalo Mini App → gắn Zalo ID vào liên hệ / tài xế (thay liên kết cũ nếu có).

    Chưa biết công ty: policy `activation_code_lookup` cho đọc đúng mã có hash này, sau đó
    chuyển context sang công ty của mã để ghi. Sai mã tính vào bộ đếm chống dò theo Zalo ID + IP.
    """
    throttle_key = f"zalo:{zalo_user_id}"
    await throttle.check(throttle_key, ip)
    code_hash = hash_code(raw_code)
    await session.execute(
        text("SELECT set_config('app.activation_code_hash', :h, true)"), {"h": code_hash}
    )
    code = await session.scalar(select(ActivationCode).where(ActivationCode.code_hash == code_hash))
    now = datetime.now(UTC)
    if code is None or code.used_at or code.revoked_at or code.expires_at <= now:
        await throttle.failed(throttle_key, ip)
        raise AppError("Mã kích hoạt không đúng hoặc đã hết hạn", code="invalid_activation_code")

    await set_tenant_context(session, company_id=code.company_id, user_id=None)
    target = ZaloTarget(contact_id=code.contact_id, user_id=code.user_id)
    if target.contact_id is not None:
        contact = await session.get(CustomerContact, target.contact_id)
        if contact is None or not contact.is_active:
            raise AppError("Liên hệ đã ngưng hoạt động", code="contact_inactive")
    else:
        assert target.user_id is not None
        await driver_target(session, code.company_id, target.user_id)

    code.used_at = now
    await session.execute(
        update(ZaloLink)
        .where(_of_target(ZaloLink, target), ZaloLink.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    link = ZaloLink(
        company_id=code.company_id,
        zalo_user_id=zalo_user_id,
        contact_id=target.contact_id,
        user_id=target.user_id,
        display_name=display_name,
        activated_at=now,
    )
    session.add(link)
    entity, entity_id = _entity(target)
    audit.record(
        session,
        code.company_id,
        entity,
        entity_id,
        "zalo_linked",
        None,
        zalo_user_id=zalo_user_id,
        display_name=display_name,
    )
    await session.flush()
    await throttle.succeeded(throttle_key)
    return link
