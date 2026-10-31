"""Log (JSON một dòng/bản ghi khi chạy production) và Sentry (nếu cấu hình DSN)."""

import json
import logging
from datetime import UTC, datetime

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup(component: str) -> None:
    """Gọi 1 lần khi khởi động tiến trình (api / worker / scheduler)."""
    settings = get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if settings.log_json
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            release=settings.release,
            server_name=component,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
        )
