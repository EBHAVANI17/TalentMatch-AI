"""Turn uploaded resume files into plain text. No guessing: unreadable files raise an error."""
import io
import json
import re

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md", "json"}

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
    "json": "application/json",
}


class UnreadableDocument(ValueError):
    """The file isn't what its extension says, or contains no extractable text (e.g. a scanned PDF)."""


def detect_type(filename: str, data: bytes) -> str:
    """Extension checked against the file's real content (magic bytes), so renamed files are rejected."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise UnreadableDocument("Unsupported file type. Upload a PDF, DOCX or TXT file.")
    if ext == "pdf" and not data.startswith(b"%PDF-"):
        raise UnreadableDocument("This file is not a valid PDF.")
    if ext == "docx" and not data.startswith(b"PK\x03\x04"):
        raise UnreadableDocument("This file is not a valid Word (.docx) document.")
    if ext in {"txt", "md", "json"}:
        if b"\x00" in data[:4096]:
            raise UnreadableDocument("This file looks binary, not text.")
    return ext


def _json_resume_to_text(data: dict) -> str:
    """JSON Resume format (jsonresume.org) to readable text."""
    parts = []
    basics = data.get("basics") or {}
    if basics:
        parts.append(f"{basics.get('name', '')} - {basics.get('label', '')}".strip(" -"))
        for key in ("summary", "email", "phone"):
            if basics.get(key):
                parts.append(str(basics[key]))
    skills = []
    for s in data.get("skills") or []:
        if isinstance(s, dict):
            skills.append(s.get("name", ""))
            skills.extend(s.get("keywords") or [])
        elif isinstance(s, str):
            skills.append(s)
    if skills:
        parts.append("Skills: " + ", ".join(k for k in skills if k))
    for w in data.get("work") or []:
        if isinstance(w, dict):
            parts.append(f"{w.get('position', '')} at {w.get('name', '')} ({w.get('startDate', '')} - {w.get('endDate', 'Present')})")
            if w.get("summary"):
                parts.append(w["summary"])
            parts.extend(f"- {h}" for h in w.get("highlights") or [])
    for e in data.get("education") or []:
        if isinstance(e, dict):
            parts.append(f"{e.get('studyType', '')} in {e.get('area', '')} from {e.get('institution', '')}")
    return "\n".join(p for p in parts if p)


def extract_text(filename: str, data: bytes) -> str:
    ext = detect_type(filename, data)
    try:
        if ext == "pdf":
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext == "docx":
            import docx

            document = docx.Document(io.BytesIO(data))
            paragraphs = [p.text for p in document.paragraphs]
            cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
            text = "\n".join(paragraphs + cells)
        elif ext == "json":
            parsed = json.loads(data.decode("utf-8"))
            text = _json_resume_to_text(parsed) if isinstance(parsed, dict) else json.dumps(parsed, indent=2)
        else:
            text = data.decode("utf-8", errors="replace")
    except UnreadableDocument:
        raise
    except Exception as exc:
        raise UnreadableDocument(f"Could not read this {ext.upper()} file. It may be damaged or password-protected.") from exc

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 20:
        raise UnreadableDocument(
            "No readable text found. If this is a scanned PDF, upload a text-based PDF or a DOCX instead."
        )
    return text
