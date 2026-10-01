from functools import lru_cache
from pathlib import Path

from app.adapters.storage.base import StorageBackend
from app.core.config import BACKEND_DIR, settings

__all__ = ["StorageBackend", "get_storage"]


@lru_cache
def get_storage() -> StorageBackend:
    backend = settings.storage_backend.lower()
    if backend == "local":
        from app.adapters.storage.local import LocalStorage
        return LocalStorage(Path(settings.storage_local_dir or BACKEND_DIR / "storage" / "documents"))
    if backend == "s3":
        from app.adapters.storage.s3 import S3Storage
        if not settings.s3_bucket_name:
            raise ValueError("STORAGE_BACKEND=s3 requires S3_BUCKET_NAME")
        return S3Storage(settings.s3_bucket_name, settings.aws_region, settings.s3_endpoint_url)
    raise ValueError(f"Unknown STORAGE_BACKEND {settings.storage_backend!r} (supported: local, s3)")
