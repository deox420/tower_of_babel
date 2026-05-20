"""DOCX metadata stripper -- zipfile + ElementTree.

A DOCX is a ZIP. Metadata lives in:

* ``docProps/core.xml`` (Dublin Core: creator, lastModifiedBy, ...)
* ``docProps/app.xml`` (Application, AppVersion, Company, Lines, ...)
* ``docProps/custom.xml`` (user-defined; removed entirely)
* ``word/document.xml`` may carry ``w:rsids`` and ``trackChanges``
  (cleaned in aggressive mode)

We re-pack the ZIP with the three docProps files replaced with
empty stubs (so Word still opens the file). custom.xml is dropped
and references to it in ``[Content_Types].xml`` and the rels file
are removed.
"""
from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

from shared.ui.diff_view import FieldRemoved
from tools.strip.diff import StripResult


_NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}

_EMPTY_CORE = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<cp:coreProperties '
    b'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    b'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    b'xmlns:dcterms="http://purl.org/dc/terms/" '
    b'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
    b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>\n'
)

_EMPTY_APP = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Properties '
    b'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
    b'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>\n'
)


def strip_docx(data: bytes, *, aggressive: bool = False) -> StripResult:
    try:
        zin = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as e:
        raise ValueError(f"not a DOCX (bad zip): {e}")

    removed: list[FieldRemoved] = []
    out_buf = io.BytesIO()
    names = set(zin.namelist())

    with zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
        # Process every member; replace or skip metadata, copy the rest.
        for info in zin.infolist():
            name = info.filename
            raw = zin.read(name)

            if name == "docProps/core.xml":
                removed.extend(_inspect_core(raw))
                _write(zout, info, _EMPTY_CORE)
                continue
            if name == "docProps/app.xml":
                removed.extend(_inspect_app(raw))
                _write(zout, info, _EMPTY_APP)
                continue
            if name == "docProps/custom.xml":
                removed.extend(_inspect_custom(raw))
                continue  # drop entirely
            if name == "[Content_Types].xml":
                cleaned = _drop_custom_from_content_types(raw)
                _write(zout, info, cleaned)
                continue
            if name == "_rels/.rels":
                cleaned = _drop_custom_from_rels(raw)
                _write(zout, info, cleaned)
                continue
            if aggressive and name == "word/document.xml":
                cleaned, scrubbed = _clean_document_xml(raw)
                removed.extend(scrubbed)
                _write(zout, info, cleaned)
                continue
            if aggressive and name == "word/settings.xml":
                cleaned, scrubbed = _clean_settings_xml(raw)
                removed.extend(scrubbed)
                _write(zout, info, cleaned)
                continue

            _write(zout, info, raw)

    if "docProps/custom.xml" in names:
        # already handled above; nothing more to do
        pass

    return StripResult(payload=out_buf.getvalue(), removed=removed)


def _write(zout: zipfile.ZipFile, info: zipfile.ZipInfo, data: bytes) -> None:
    new_info = zipfile.ZipInfo(filename=info.filename,
                               date_time=(1980, 1, 1, 0, 0, 0))
    new_info.compress_type = info.compress_type or zipfile.ZIP_DEFLATED
    new_info.external_attr = info.external_attr
    zout.writestr(new_info, data)


# Standard DOCX core.xml elements (Dublin Core subset OOXML uses).
_STANDARD_CORE_ELEMENTS = (
    "title", "subject", "creator", "keywords", "description",
    "lastModifiedBy", "revision", "lastPrinted", "created", "modified",
    "category", "contentStatus",
)

# Common DOCX app.xml elements.
_STANDARD_APP_ELEMENTS = (
    "Template", "TotalTime", "Pages", "Words", "Characters",
    "Application", "AppVersion", "Company", "Manager", "Lines",
    "Paragraphs", "CharactersWithSpaces",
)


def _inspect_core(raw: bytes) -> list[FieldRemoved]:
    rows: list[FieldRemoved] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [FieldRemoved("DOCX.core", "(malformed XML)")]

    seen: set[str] = set()
    for child in root:
        # child.tag is like "{http://purl.org/dc/elements/1.1/}creator"
        local = child.tag.split("}", 1)[-1]
        seen.add(local)
        text = (child.text or "").strip()
        rows.append(FieldRemoved(
            f"DOCX.core.{local}", text[:80] if text else "(empty)",
        ))
    # `(not present)` rows for the standard elements not in the file.
    for elem in _STANDARD_CORE_ELEMENTS:
        if elem not in seen:
            rows.append(FieldRemoved(f"DOCX.core.{elem}", "(not present)"))
    return rows


def _inspect_app(raw: bytes) -> list[FieldRemoved]:
    rows: list[FieldRemoved] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [FieldRemoved("DOCX.app", "(malformed XML)")]

    seen: set[str] = set()
    for child in root:
        local = child.tag.split("}", 1)[-1]
        seen.add(local)
        text = (child.text or "").strip()
        rows.append(FieldRemoved(
            f"DOCX.app.{local}", text[:80] if text else "(empty)",
        ))
    for elem in _STANDARD_APP_ELEMENTS:
        if elem not in seen:
            rows.append(FieldRemoved(f"DOCX.app.{elem}", "(not present)"))
    return rows


def _inspect_custom(raw: bytes) -> list[FieldRemoved]:
    rows: list[FieldRemoved] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [FieldRemoved("DOCX.custom", "(malformed XML)")]

    for child in root:
        # <property name="Foo"><vt:lpwstr>bar</vt:lpwstr></property>
        pname = child.attrib.get("name", "?")
        text = "".join(t.text or "" for t in child).strip()
        rows.append(FieldRemoved(f"DOCX.custom.{pname}", text[:80] or "(empty)"))

    if not rows:
        rows.append(FieldRemoved("DOCX.custom", "(file removed)"))
    return rows


_CUSTOM_RE = re.compile(
    rb'<Override\b[^>]*PartName="/?docProps/custom\.xml"[^>]*/>'
)
_CUSTOM_REL_RE = re.compile(
    rb'<Relationship\b[^>]*Target="/?docProps/custom\.xml"[^>]*/>'
)


def _drop_custom_from_content_types(raw: bytes) -> bytes:
    return _CUSTOM_RE.sub(b"", raw)


def _drop_custom_from_rels(raw: bytes) -> bytes:
    return _CUSTOM_REL_RE.sub(b"", raw)


_RSID_ATTR_RE = re.compile(
    rb'\s+w:rsid[A-Z][A-Za-z]*="[0-9A-Fa-f]+"'
)
_TRACK_CHANGES_TAGS = (b"w:ins", b"w:del", b"w:moveFrom", b"w:moveTo")


def _clean_document_xml(raw: bytes) -> tuple[bytes, list[FieldRemoved]]:
    rows: list[FieldRemoved] = []
    if _RSID_ATTR_RE.search(raw):
        rows.append(FieldRemoved("DOCX.rsids", "revision-save IDs"))
    cleaned = _RSID_ATTR_RE.sub(b"", raw)

    for tag in _TRACK_CHANGES_TAGS:
        if b"<" + tag in cleaned:
            rows.append(FieldRemoved(
                f"DOCX.document.{tag.decode()}", "track-changes mark"))
            # Strip the tag wrappers but keep their inner content so the
            # visible document text doesn't disappear.
            cleaned = re.sub(
                rb"<" + tag + rb"\b[^>]*>", b"", cleaned)
            cleaned = re.sub(
                rb"</" + tag + rb">", b"", cleaned)

    return cleaned, rows


def _clean_settings_xml(raw: bytes) -> tuple[bytes, list[FieldRemoved]]:
    rows: list[FieldRemoved] = []
    cleaned = raw
    if b"<w:rsids>" in cleaned:
        rows.append(FieldRemoved("DOCX.settings.rsids", "rsid table"))
        cleaned = re.sub(
            rb"<w:rsids>.*?</w:rsids>", b"", cleaned, flags=re.DOTALL)
    if b"<w:trackChanges" in cleaned:
        rows.append(FieldRemoved("DOCX.settings.trackChanges", "enabled flag"))
        cleaned = re.sub(rb"<w:trackChanges[^/]*/>", b"", cleaned)
    return cleaned, rows


__all__ = ["strip_docx"]
