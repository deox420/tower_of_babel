"""PDF metadata stripper -- pypdf-backed.

Stripped surfaces:

* ``/Info`` dict (Author, Title, Producer, Creator, CreationDate,
  ModDate, Keywords, Subject)
* ``/Metadata`` XMP stream on the document catalog
* ``/ID`` array on the trailer (replaced with a fresh random pair,
  not blanked -- some PDF readers refuse files with a missing /ID)

Encrypted inputs are not silently passed through: ``strip_pdf``
raises ``EncryptedPDFError`` so the caller can refuse with the
right exit code (docs/tools/STRIP.md table: exit 4).
"""
from __future__ import annotations

import io
import secrets

from shared.ui.diff_view import FieldRemoved
from tools.strip.diff import StripResult


class EncryptedPDFError(ValueError):
    """Raised when the input PDF is encrypted -- STRIP refuses these."""


# Standard /Info dict keys per PDF 1.7 §14.3.3. Reported as
# `(not present)` when the file doesn't carry them.
_STANDARD_INFO_KEYS = (
    "Title", "Author", "Subject", "Keywords",
    "Creator", "Producer", "CreationDate", "ModDate", "Trapped",
)


def strip_pdf(data: bytes, *, aggressive: bool = False) -> StripResult:
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.errors import PdfReadError
    except ImportError as e:  # pragma: no cover -- runtime dep
        raise RuntimeError(
            "STRIP needs `pypdf` to process PDFs. "
            "Install with: pip install pypdf>=4.0"
        ) from e

    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as e:
        raise ValueError(f"not a readable PDF: {e}") from e

    if reader.is_encrypted:
        raise EncryptedPDFError("PDF is encrypted; STRIP refuses to guess passwords")

    removed: list[FieldRemoved] = []

    # /Info dict.
    info = reader.metadata
    if info:
        for k, v in info.items():
            key = str(k).lstrip("/")
            removed.append(FieldRemoved(f"PDF.Info.{key}", str(v)[:120]))

    # XMP metadata on the catalog.
    try:
        catalog = reader.trailer["/Root"]
        if "/Metadata" in catalog:
            xmp_obj = catalog["/Metadata"]
            try:
                xmp_bytes = xmp_obj.get_data()  # type: ignore[attr-defined]
                removed.append(FieldRemoved(
                    "PDF.Metadata", f"XMP stream, {len(xmp_bytes)} bytes"))
            except Exception:
                removed.append(FieldRemoved("PDF.Metadata", "XMP stream"))
    except Exception:
        pass

    # /ID array on the trailer.
    if "/ID" in reader.trailer:
        try:
            old_id = reader.trailer["/ID"]
            removed.append(FieldRemoved("PDF.ID",
                                        f"{len(old_id)}-element array"))
        except Exception:
            removed.append(FieldRemoved("PDF.ID", "(present)"))
    else:
        removed.append(FieldRemoved("PDF.ID", "(not present)"))

    # `(not present)` rows for every standard /Info key the file does
    # not carry — same UX pattern as JPEG/PNG.
    seen_info_keys: set[str] = {
        row.field[len("PDF.Info."):]
        for row in removed if row.field.startswith("PDF.Info.")
    }
    for k in _STANDARD_INFO_KEYS:
        if k not in seen_info_keys:
            removed.append(FieldRemoved(f"PDF.Info.{k}", "(not present)"))
    # Also report XMP `(not present)` if the catalog didn't carry it.
    if not any(row.field == "PDF.Metadata" for row in removed):
        removed.append(FieldRemoved("PDF.Metadata", "(not present)"))

    # Build a fresh writer with just the pages. Not cloning the document
    # catalog avoids carrying /Info, /Metadata, and assorted document-level
    # surfaces that would otherwise leak. Page-level annotations and form
    # fields are preserved by add_page.
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    payload = out.getvalue()

    # Replace /ID array with a fresh random pair. pypdf may have copied the
    # old one in trailer construction; the fastest reliable fix is a tiny
    # post-pass at the byte level.
    payload = _replace_id_array(payload)

    return StripResult(payload=payload, removed=removed)


def _replace_id_array(pdf_bytes: bytes) -> bytes:
    """Replace the ``/ID [ <..> <..> ]`` array with two fresh 16-byte IDs.

    Done at the byte level because pypdf's trailer-write path doesn't
    expose /ID through a stable public API across versions. Falls back
    to a no-op if no /ID is found.
    """
    import re

    new_a = secrets.token_hex(16)
    new_b = secrets.token_hex(16)
    replacement = (f"/ID [ <{new_a}> <{new_b}> ]").encode("latin-1")

    pat = re.compile(rb"/ID\s*\[\s*<[^>]+>\s*<[^>]+>\s*\]")
    if pat.search(pdf_bytes):
        return pat.sub(replacement, pdf_bytes, count=1)

    pat2 = re.compile(rb"/ID\s*\[\s*\([^)]*\)\s*\([^)]*\)\s*\]")
    if pat2.search(pdf_bytes):
        return pat2.sub(replacement, pdf_bytes, count=1)

    return pdf_bytes


__all__ = ["strip_pdf", "EncryptedPDFError"]
