from typing import Protocol


class StorageBackend(Protocol):
    """Where file bytes live. Keys are relative paths like 'orgs/org_x/candidates/cand_y/doc_z/cv.pdf'."""

    name: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def presigned_url(self, key: str, filename: str, content_type: str, expires_in: int) -> str | None:
        """A time-limited direct download URL, or None if the backend can't make one (local disk)."""
        ...
