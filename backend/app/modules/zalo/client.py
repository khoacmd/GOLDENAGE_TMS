"""Zalo Open API: đổi access token người dùng lấy Zalo ID, đổi token vị trí lấy tọa độ."""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import get_settings
from app.core.errors import AuthenticationError

log = logging.getLogger(__name__)
TIMEOUT_S = 10


@dataclass(frozen=True)
class ZaloProfile:
    id: str  # Zalo ID theo ứng dụng (mỗi Mini App một ID khác nhau)
    name: str | None


@dataclass(frozen=True)
class ZaloLocation:
    latitude: Decimal
    longitude: Decimal


def _mock_profile(access_token: str) -> ZaloProfile:
    # "mock:<zalo_id>:<tên>" - chỉ dùng ở dev/test (TMS_ZALO_MOCK=true).
    _, zalo_id, *name = access_token.split(":", 2)
    if not zalo_id:
        raise AuthenticationError("Token Zalo giả lập không hợp lệ")
    return ZaloProfile(id=zalo_id, name=name[0] if name else None)


async def fetch_profile(access_token: str) -> ZaloProfile:
    settings = get_settings()
    if settings.zalo_mock and access_token.startswith("mock:"):
        return _mock_profile(access_token)
    if not settings.zalo_app_secret:
        raise AuthenticationError("Máy chủ chưa cấu hình Zalo Mini App")
    # appsecret_proof = HMAC-SHA256(access_token, app secret) - xác nhận token cấp cho app của mình.
    proof = hmac.new(
        settings.zalo_app_secret.encode(), access_token.encode(), hashlib.sha256
    ).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            resp = await client.get(
                settings.zalo_graph_url,
                # Token mặc định chỉ cho phép lấy ID; tên cần người dùng cấp quyền scope.userInfo.
                params={"fields": "id"},
                headers={"access_token": access_token, "appsecret_proof": proof},
            )
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthenticationError("Không kết nối được Zalo, vui lòng thử lại") from exc
    if body.get("error") or not body.get("id"):
        raise AuthenticationError("Phiên Zalo không hợp lệ hoặc đã hết hạn")
    return ZaloProfile(id=str(body["id"]), name=body.get("name"))


async def fetch_location(access_token: str, location_token: str) -> ZaloLocation | None:
    """Đổi token của `getLocation` lấy tọa độ qua server Zalo (dùng 1 lần, hạn 2 phút).

    Tọa độ lấy từ Zalo nên client không tự khai được. Lỗi → None (coi như không có vị trí)."""
    settings = get_settings()
    if settings.zalo_mock and location_token.startswith("mock:"):
        latitude, longitude = location_token.removeprefix("mock:").split(",")
        return ZaloLocation(Decimal(latitude), Decimal(longitude))
    if not settings.zalo_app_secret:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            resp = await client.get(
                f"{settings.zalo_graph_url}/info",
                headers={
                    "access_token": access_token,
                    "code": location_token,
                    "secret_key": settings.zalo_app_secret,
                },
            )
        body = resp.json()
        data = body.get("data") or {}
        if not body.get("error") and data.get("latitude") and data.get("longitude"):
            return ZaloLocation(Decimal(data["latitude"]), Decimal(data["longitude"]))
        log.warning("Zalo không trả vị trí: error=%s", body.get("error"))
    except (httpx.HTTPError, ValueError, InvalidOperation) as exc:
        log.warning("Không lấy được vị trí từ Zalo: %s", type(exc).__name__)
    return None
