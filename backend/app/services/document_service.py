"""Stored files: validation, storage keys, access rules and signed download links."""
import hashlib
import hmac
import time
import uuid
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.storage import get_storage
from app.core.config import settings
from app.core.tenancy import TenantContext, can_view_candidate
from app.models.db_models import CandidateProfile, Document, User
from app.services.candidate_service import contact_visible_ids
from app.services.text_extraction import CONTENT_TYPES, UnreadableDocument, detect_type


def store_file(
    db: Session,
    *,
    data: bytes,
    filename: str,
    kind: str,
    uploaded_by: User,
    candidate: Optional[CandidateProfile] = None,
    organization_id: Optional[str] = None,
) -> Document:
    """Validate and store a file. The caller commits."""
    limit = settings.max_upload_mb * 1024 * 1024
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Files must be {settings.max_upload_mb} MB or smaller.")
    try:
        ext = detect_type(filename, data)
    except UnreadableDocument as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))

    doc_id = f"doc_{uuid.uuid4().hex[:16]}"
    owner_scope = f"orgs/{organization_id}" if organization_id else "talent"
    subject = f"candidates/{candidate.id}" if candidate else "files"
    key = f"{owner_scope}/{subject}/{doc_id}/{filename}"
    storage = get_storage()
    storage.put(key, data, CONTENT_TYPES[ext])

    document = Document(
        id=doc_id,
        organization_id=organization_id,
        candidate_id=candidate.id if candidate else None,
        uploaded_by_user_id=uploaded_by.id,
        kind=kind,
        filename=filename,
        content_type=CONTENT_TYPES[ext],
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_backend=storage.name,
        storage_key=key,
    )
    db.add(document)
    return document


def can_access(db: Session, ctx: TenantContext, document: Document) -> bool:
    """Same rule as contact details: a resume reveals who someone is and how to reach them."""
    if ctx.is_super_admin or document.uploaded_by_user_id == ctx.user.id:
        return True
    if document.candidate_id:
        candidate = db.get(CandidateProfile, document.candidate_id)
        if candidate is None or not can_view_candidate(db, ctx, candidate):
            return False
        return candidate.id in contact_visible_ids(db, ctx, [candidate.id])
    return bool(document.organization_id) and document.organization_id == ctx.org_id


# ---------------------------------------------------------------------------
# Signed download links (for storage backends without native presigned URLs)
# ---------------------------------------------------------------------------
def _signature(document_id: str, expires: int) -> str:
    message = f"{document_id}:{expires}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).hexdigest()


def download_url(document: Document) -> Tuple[str, int]:
    """(url, expires_at_unix). Anyone holding the URL can download until it expires."""
    ttl = settings.download_url_ttl_seconds
    expires = int(time.time()) + ttl
    url = get_storage().presigned_url(document.storage_key, document.filename, document.content_type, ttl)
    if url is None:
        url = f"{settings.api_prefix}/documents/{document.id}/content?expires={expires}&signature={_signature(document.id, expires)}"
    return url, expires


def verify_signature(document_id: str, expires: int, signature: str) -> bool:
    if expires < time.time():
        return False
    return hmac.compare_digest(_signature(document_id, expires), signature)
