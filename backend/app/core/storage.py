"""Object storage behind one small interface.

- `S3Storage`: MinIO locally, any S3-compatible store in the cloud.
- `LocalStorage`: a folder on disk, for development without Docker and for tests.
Moving to Azure Blob Storage means adding one more implementation, not touching callers.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import anyio

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]{0,499}$")


class StorageError(Exception):
    pass


class ObjectNotFoundError(StorageError):
    pass


def validate_key(key: str) -> str:
    if not _SAFE_KEY.match(key) or ".." in key or "//" in key:
        raise StorageError(f"Unsafe storage key: {key!r}")
    return key


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("Key escapes the storage root")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await anyio.Path(path.parent).mkdir(parents=True, exist_ok=True)
        await anyio.Path(path).write_bytes(data)

    async def get(self, key: str) -> bytes:
        path = anyio.Path(self._path(key))
        if not await path.exists():
            raise ObjectNotFoundError(key)
        return await path.read_bytes()

    async def delete(self, key: str) -> None:
        path = anyio.Path(self._path(key))
        if await path.exists():
            await path.unlink()


class S3Storage:
    def __init__(self, settings: Settings, bucket: str):
        import boto3  # imported lazily: not needed for local storage or tests

        self.bucket = bucket
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=(
                settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else None
            ),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        # Encryption at rest is a bucket policy (MinIO/S3/Azure), not a per-object flag.
        await anyio.to_thread.run_sync(
            lambda: self._client.put_object(
                Bucket=self.bucket, Key=validate_key(key), Body=data, ContentType=content_type
            )
        )

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            try:
                response = self._client.get_object(Bucket=self.bucket, Key=validate_key(key))
            except self._client.exceptions.NoSuchKey as exc:
                raise ObjectNotFoundError(key) from exc
            return response["Body"].read()

        return await anyio.to_thread.run_sync(_get)

    async def delete(self, key: str) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.delete_object(Bucket=self.bucket, Key=validate_key(key))
        )


@lru_cache(maxsize=4)
def _build(backend: str, bucket: str) -> ObjectStorage:
    settings = get_settings()
    if backend == "local":
        return LocalStorage(Path(settings.local_storage_path) / bucket)
    return S3Storage(settings, bucket)


def resume_storage() -> ObjectStorage:
    settings = get_settings()
    return _build(settings.storage_backend, settings.s3_bucket_resumes)
