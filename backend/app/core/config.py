from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-in-prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TMS_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"

    # Runtime dùng role tms_app (chịu RLS); migration dùng role tms_owner.
    database_url: str = "postgresql+asyncpg://tms_app:tms_app@localhost:55432/tms"
    migration_database_url: str = "postgresql+asyncpg://tms_owner:tms_owner@localhost:55432/tms"

    jwt_secret: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    business_timezone: str = "Asia/Ho_Chi_Minh"
    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def _check_prod_secrets(self) -> "Settings":
        if self.env == "prod" and (self.jwt_secret == _DEV_JWT_SECRET or len(self.jwt_secret) < 32):
            raise ValueError("TMS_JWT_SECRET phải được cấu hình (>= 32 ký tự) ở môi trường prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
