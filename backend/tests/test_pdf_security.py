import io
import subprocess

import pytest
from pypdf import PdfWriter
from realty import documents
from realty.models import Document
from realty.security import Principal


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("blank", "ocr_required"),
        ("javascript", "extraction_failed"),
        ("encrypted", "extraction_failed"),
        ("malformed", "extraction_failed"),
        ("pages", "extraction_failed"),
    ],
)
def test_untrusted_pdf_parser_runs_in_bounded_child(factory, account, kind, expected):
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if kind == "javascript":
        writer.add_js("app.alert('untrusted')")
    if kind == "encrypted":
        writer.encrypt("fictional-password")
    if kind == "pages":
        for _ in range(100):
            writer.add_blank_page(width=72, height=72)
    stream = io.BytesIO()
    writer.write(stream)
    content = b"%PDF-1.7\ninvalid" if kind == "malformed" else stream.getvalue()
    org_id = account["organization"]["id"]
    actor = Principal(account["user"]["id"], org_id, "owner", "unused-session")
    with factory() as db:
        db.info["org_id"] = org_id
        document = documents.upload(db, actor, "test.pdf", content, None)
        documents.extract_pdf(db, document)
        assert document.status == expected
        db.rollback()


def test_pdf_timeout_is_visible_and_child_has_no_application_secrets(monkeypatch, factory):
    class MemoryStorage:
        def get(self, key):
            return b"%PDF-1.7"

    monkeypatch.setattr(documents, "storage", MemoryStorage)
    monkeypatch.setenv("AI_API_KEY", "must-not-reach-parser")

    def timeout(command, **kwargs):
        assert "AI_API_KEY" not in kwargs["env"]
        assert kwargs["timeout"] == 30
        assert "-I" in command
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(documents.subprocess, "run", timeout)
    document = Document(storage_key="test.pdf")
    with factory() as db:
        documents.extract_pdf(db, document)
        assert document.status == "extraction_failed"
