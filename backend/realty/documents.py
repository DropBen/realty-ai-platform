import hashlib
import io
from pathlib import Path
from typing import Protocol, cast

from azure.storage.blob import BlobServiceClient
from pypdf import PdfReader
from pypdf.generic import DictionaryObject
from sqlalchemy.orm import Session

from realty.config import settings
from realty.db import uid
from realty.errors import DomainError
from realty.models import Document, Usage
from realty.repository import validate_refs
from realty.security import Principal, audit

MAX_UPLOAD = 10 * 1024 * 1024


class ObjectStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def path(self, key: str) -> Path:
        root = Path(settings.storage_path).resolve()
        candidate = (root / key).resolve()
        if not candidate.is_relative_to(root):
            raise DomainError("invalid_storage_key", "Invalid storage key.")
        return candidate

    def put(self, key: str, content: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


class AzureStorage:
    def __init__(self) -> None:
        self.container = BlobServiceClient.from_connection_string(
            settings.storage_connection_string
        ).get_container_client(settings.storage_container)

    def put(self, key: str, content: bytes) -> None:
        self.container.upload_blob(key, content, overwrite=False)

    def get(self, key: str) -> bytes:
        return self.container.download_blob(key).readall()  # type: ignore[no-any-return]

    def delete(self, key: str) -> None:
        self.container.delete_blob(key)


def storage() -> ObjectStorage:
    if settings.storage_backend == "azure":
        if not settings.storage_connection_string:
            raise DomainError("storage_unconfigured", "Document storage is not configured.", 503)
        return AzureStorage()
    return LocalStorage()


def upload(
    db: Session, actor: Principal, name: str, content: bytes, contact_id: str | None
) -> Document:
    actor.require("write")
    validate_refs(db, {"contact_id": contact_id})
    if not content or len(content) > MAX_UPLOAD:
        raise DomainError("invalid_size", "Choose a file between 1 byte and 10 MB.", 413)
    filename = Path(name.replace("\\", "/")).name[:250]
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DomainError("invalid_file", "Text files must use UTF-8 encoding.", 422) from exc
        mime, status = "text/plain", "extracted"
    elif suffix == ".pdf" and content.startswith(b"%PDF-"):
        # PDF extraction is a background operation. Downloads are attachments, never inline.
        text, mime, status = "", "application/pdf", "pending_extraction"
    else:
        raise DomainError("invalid_file", "Only UTF-8 text and PDF documents are supported.", 422)
    key = actor.org_id + "/" + uid() + suffix
    storage().put(key, content)
    document = Document(
        org_id=actor.org_id,
        contact_id=contact_id,
        name=filename,
        mime_type=mime,
        storage_key=key,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        text=text[:100000],
        status=status,
    )
    db.add(document)
    try:
        db.flush()
    except Exception:
        storage().delete(key)
        raise
    audit(db, actor, "document.uploaded", document.id)
    return document


def extract_pdf(db: Session, document: Document) -> None:
    try:
        reader = PdfReader(io.BytesIO(storage().get(document.storage_key)), strict=True)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("Encrypted or oversized PDF")
        root = cast(DictionaryObject, reader.trailer["/Root"])
        if "/OpenAction" in root or "/AA" in root:
            raise ValueError("Active PDF content")
        document.text = "\n".join(page.extract_text()[:20000] for page in reader.pages)[:100000]
        document.status = "extracted" if document.text.strip() else "ocr_required"
        db.add(Usage(org_id=document.org_id, metric="documents_processed", source_id=document.id))
    except Exception:
        document.status = "extraction_failed"


class TranscriptionProvider(Protocol):
    """Future call ingestion port. No live telephony is advertised."""

    def transcribe(self, recording: bytes, mime_type: str) -> str: ...


class OCRProvider(Protocol):
    """Provider extension for scanned documents; status remains ocr_required until configured."""

    def extract(self, content: bytes) -> str: ...
