"""Lưu file (ảnh chứng từ giao hàng) trên S3-compatible; bản in-memory cho test."""

import asyncio
from functools import lru_cache
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    def url(self, key: str, expires: int = 600) -> str: ...


class S3Storage:
    def __init__(self) -> None:
        s = get_settings()
        self.bucket = s.s3_bucket
        common = {
            "aws_access_key_id": s.s3_access_key,
            "aws_secret_access_key": s.s3_secret_key,
            "region_name": s.s3_region,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self.client = boto3.client("s3", endpoint_url=s.s3_endpoint, **common)  # type: ignore[call-overload]
        # Client riêng để ký URL theo địa chỉ trình duyệt truy cập được.
        self.public = boto3.client(  # type: ignore[call-overload]
            "s3", endpoint_url=s.s3_public_endpoint or s.s3_endpoint, **common
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        self._bucket_ready = True

    def _put(self, key: str, data: bytes, content_type: str) -> None:
        self._ensure_bucket()
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._put, key, data, content_type)

    def _exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._exists, key)

    def url(self, key: str, expires: int = 600) -> str:
        return str(
            self.public.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
            )
        )


class MemoryStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.files[key] = (data, content_type)

    async def exists(self, key: str) -> bool:
        return key in self.files

    def url(self, key: str, expires: int = 600) -> str:
        return f"memory://{key}"


@lru_cache
def get_storage() -> Storage:
    return MemoryStorage() if get_settings().storage_backend == "memory" else S3Storage()
