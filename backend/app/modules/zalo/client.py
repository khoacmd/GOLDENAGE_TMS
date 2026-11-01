"""Zalo Open API: đổi access token người dùng (`getAccessToken()` của Mini App) lấy Zalo ID."""

import hashlib
import hmac
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.errors import AuthenticationError

TIMEOUT_S = 10


@dataclass(frozen=True)
class ZaloProfile:
    id: str  # Zalo ID theo ứng dụng (mỗi Mini App một ID khác nhau)
    name: str | None


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
                params={"fields": "id,name"},
                headers={"access_token": access_token, "appsecret_proof": proof},
            )
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AuthenticationError("Không kết nối được Zalo, vui lòng thử lại") from exc
    if body.get("error") or not body.get("id"):
        raise AuthenticationError("Phiên Zalo không hợp lệ hoặc đã hết hạn")
    return ZaloProfile(id=str(body["id"]), name=body.get("name"))
