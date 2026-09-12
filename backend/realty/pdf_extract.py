"""Bounded PDF text parser, executed in a separate process without application secrets."""

import io
import json
import sys
from typing import cast


def main() -> None:
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    from pypdf import PdfReader
    from pypdf.generic import DictionaryObject

    content = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("PDF exceeds size limit")
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted or len(reader.pages) > 100:
        raise ValueError("Encrypted or oversized PDF")
    root = cast(DictionaryObject, reader.trailer["/Root"])
    names = root.get("/Names", {})
    if names:
        names = names.get_object()
    if any(key in root for key in ["/OpenAction", "/AA"]) or any(
        key in names for key in ["/JavaScript", "/EmbeddedFiles"]
    ):
        raise ValueError("Active PDF content")
    chunks: list[str] = []
    remaining = 100000
    for page in reader.pages:
        if "/AA" in page:
            raise ValueError("Active page content")
        for reference in page.get("/Annots", []):
            annotation = reference.get_object()
            action = annotation.get("/A")
            if "/AA" in annotation or (
                action
                and action.get_object().get("/S") in {"/JavaScript", "/Launch", "/SubmitForm"}
            ):
                raise ValueError("Active annotation")
        # Inspect every page for active content even after reaching the text limit.
        if remaining > 0:
            extracted = (page.extract_text() or "")[: min(20000, remaining)]
            chunks.append(extracted)
            remaining -= len(extracted) + 1
    sys.stdout.write(json.dumps({"text": "\n".join(chunks)[:100000]}))


if __name__ == "__main__":
    main()
