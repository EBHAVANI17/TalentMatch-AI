"""File storage: validated uploads, real text extraction, access rules and signed download links."""
import io
import time

import pytest

from app.adapters.storage.local import LocalStorage
from app.core.database import SessionLocal
from app.models.db_models import Document, Resume
from app.services import document_service

RESUME_TEXT = (
    b"Aarav Sharma\nStaff AI Engineer\nSkills: Python, PyTorch, Kubernetes, PostgreSQL\n"
    b"6 years building distributed inference systems at scale."
)


def _upload(client, headers, filename, data, candidate_id="cand_001"):
    return client.post(
        "/api/v1/resumes/upload", headers=headers,
        files={"file": (filename, data, "application/octet-stream")}, data={"candidate_id": candidate_id},
    )


def _latest_document(candidate_id="cand_001"):
    with SessionLocal() as db:
        resume = db.query(Resume).filter(Resume.candidate_id == candidate_id).order_by(Resume.created_at.desc()).first()
        return db.get(Document, resume.document_id)


def _docx_bytes(text):
    import docx

    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _blank_pdf_bytes():
    import pypdf

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_upload_stores_file_and_signed_link_downloads_it(client, auth):
    h = auth("aarav")
    res = _upload(client, h, "aarav_cv.txt", RESUME_TEXT)
    assert res.status_code == 200, res.text
    doc = _latest_document()
    assert doc.size_bytes == len(RESUME_TEXT) and doc.content_type == "text/plain" and len(doc.sha256) == 64
    assert doc.storage_key.startswith("talent/candidates/cand_001/")

    link = client.post(f"/api/v1/documents/{doc.id}/download-url", headers=h)
    assert link.status_code == 200
    url = link.json()["url"]
    # The signed link works without a login...
    download = client.get(url)
    assert download.status_code == 200 and download.content == RESUME_TEXT
    assert "attachment" in download.headers["content-disposition"]
    # ...but not if tampered with or expired
    assert client.get(url[:-4] + "0000").status_code == 403
    expired = int(time.time()) - 1
    sig = document_service._signature(doc.id, expired)
    assert client.get(f"/api/v1/documents/{doc.id}/content?expires={expired}&signature={sig}").status_code == 403


def test_docx_text_is_really_extracted(client, auth):
    res = _upload(client, auth("aarav"), "cv.docx", _docx_bytes(RESUME_TEXT.decode()))
    assert res.status_code == 200, res.text
    with SessionLocal() as db:
        resume = db.get(Resume, res.json()["id"])
        assert "PyTorch" in resume.candidate.raw_resume_text


def test_renamed_or_unreadable_files_are_rejected(client, auth):
    h = auth("aarav")
    assert _upload(client, h, "fake.pdf", b"this is not a pdf at all").status_code == 415
    assert _upload(client, h, "virus.exe", b"MZ....").status_code == 415
    scanned = _upload(client, h, "scanned.pdf", _blank_pdf_bytes())
    assert scanned.status_code == 422 and "No readable text" in scanned.json()["detail"]
    assert _upload(client, h, "empty.txt", b"").status_code == 400


def test_size_limit(client, auth, monkeypatch):
    monkeypatch.setattr(document_service.settings, "max_upload_mb", 0)
    assert _upload(client, auth("aarav"), "cv.txt", RESUME_TEXT).status_code == 413


def test_document_access_follows_contact_privacy(client, auth):
    _upload(client, auth("aarav"), "aarav_cv.txt", RESUME_TEXT)
    doc = _latest_document()
    # Aarav applied to Anthropic (job_001) but not to Stripe
    assert client.get(f"/api/v1/documents/{doc.id}", headers=auth("anthropic")).status_code == 200
    assert client.post(f"/api/v1/documents/{doc.id}/download-url", headers=auth("stripe")).status_code == 404
    assert client.get(f"/api/v1/documents/{doc.id}", headers=auth("elena")).status_code == 404
    assert client.get(f"/api/v1/documents/{doc.id}", headers=auth("admin")).status_code == 200


def test_recruiter_can_upload_resume_for_sourced_candidate(client, auth):
    stripe = auth("stripe")
    cand = client.post("/api/v1/candidates", headers=stripe, json={
        "full_name": "Uma Uploaded", "email": f"uma.{time.time_ns()}@example.com",
    }).json()
    res = _upload(client, stripe, "uma.txt", RESUME_TEXT, candidate_id=cand["id"])
    assert res.status_code == 200, res.text
    doc = _latest_document(cand["id"])
    assert doc.storage_key.startswith("orgs/org_stripe/candidates/")
    # Another organization can't upload to (or see) them
    assert _upload(client, auth("anthropic"), "x.txt", RESUME_TEXT, candidate_id=cand["id"]).status_code == 404


def test_local_storage_rejects_keys_outside_root(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.put("../escape.txt", b"x", "text/plain")


def test_s3_presigned_urls(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    from app.adapters.storage.s3 import S3Storage

    url = S3Storage("talentmatch-docs", region="ap-south-1").presigned_url("talent/x/cv.pdf", "cv.pdf", "application/pdf", 300)
    assert "talentmatch-docs" in url and "X-Amz-Signature=" in url and "Expires=300" in url
