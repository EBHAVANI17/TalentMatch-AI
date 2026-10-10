from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.storage import get_storage
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant
from app.models.db_models import Document
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["Documents"])


class DocumentOut(BaseModel):
    id: str
    candidate_id: Optional[str] = None
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: Optional[datetime] = None


class DownloadLink(BaseModel):
    url: str
    expires_at: datetime


def _visible_document(db: Session, ctx: TenantContext, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or not document_service.can_access(db, ctx, document):
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    return DocumentOut.model_validate(_visible_document(db, ctx, document_id), from_attributes=True)


@router.post("/{document_id}/download-url", response_model=DownloadLink)
def create_download_link(document_id: str, db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant)):
    """A short-lived link that can be opened directly in the browser."""
    document = _visible_document(db, ctx, document_id)
    url, expires = document_service.download_url(document)
    return DownloadLink(url=url, expires_at=datetime.fromtimestamp(expires, tz=timezone.utc))


@router.get("/{document_id}/content", include_in_schema=False)
def download_content(
    document_id: str,
    expires: int = Query(...),
    signature: str = Query(..., min_length=64, max_length=64),
    db: Session = Depends(get_db),
):
    """Target of signed links for local storage. The signature is the authorization."""
    if not document_service.verify_signature(document_id, expires, signature):
        raise HTTPException(status_code=403, detail="This download link is invalid or has expired")
    from app.db.functions import document_for_signed_download  # no session here: the signature authorizes
    document = document_for_signed_download(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=get_storage().get(document["storage_key"]),
        media_type=document["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{document["filename"]}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
