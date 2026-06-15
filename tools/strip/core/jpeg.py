"""JPEG metadata stripper -- stdlib only, byte-level marker walker.

JPEG is a stream of marker segments. We re-emit only the segments
that carry image data (SOF, DHT, DQT, SOS + entropy data, EOI) and
JFIF (APP0); everything else identified as metadata is dropped and
named in the diff. A focused TIFF parser unpacks EXIF (APP1) so the
diff lists individual fields (Make, Model, GPS, ...) rather than
"EXIF (3210 bytes)".

Aggressive mode additionally strips APP2 (ICC profile) and APP14
(Adobe authoring tag). The JFIF APP0 is always kept; it's a format
marker, not user data.

Per-segment behaviour matches the table in docs/tools/STRIP.md
Section 2.
"""
from __future__ import annotations

import struct

from shared.ui.diff_view import FieldRemoved
from tools.strip.diff import StripResult


# Standalone markers (no length, no payload).
_STANDALONE = {0x01} | set(range(0xd0, 0xd8))  # TEM + RST0..RST7

# Markers that carry image payload (length-prefixed, but we keep them).
_KEEP_ALWAYS = {
    0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
    0xc8, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf,  # SOFn (incl. progressive)
    0xc4,  # DHT
    0xdb,  # DQT
    0xdd,  # DRI
    0xe0,  # APP0 (JFIF) -- kept; it's a format marker
}


def _read_u16_be(buf: bytes, offset: int) -> int:
    return (buf[offset] << 8) | buf[offset + 1]


def strip_jpeg(data: bytes, *, aggressive: bool = False) -> StripResult:
    if len(data) < 4 or data[0] != 0xff or data[1] != 0xd8:
        raise ValueError("not a JPEG (no SOI marker)")

    out = bytearray(b"\xff\xd8")
    removed: list[FieldRemoved] = []

    i = 2
    n = len(data)

    while i < n:
        # JPEG allows arbitrary 0xff fill bytes between markers.
        if data[i] != 0xff:
            out.extend(data[i:])
            break
        while i < n and data[i] == 0xff:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1

        if marker == 0x00:
            continue  # stuffed FF 00 inside entropy data (shouldn't happen here)
        if marker == 0xd9:  # EOI
            out.extend(b"\xff\xd9")
            break
        if marker in _STANDALONE:
            out.append(0xff)
            out.append(marker)
            continue
        if marker == 0xda:  # SOS -- entropy-coded data runs to EOI
            if i + 2 > n:
                break
            length = _read_u16_be(data, i)
            if i + length > n:
                length = n - i
            out.append(0xff)
            out.append(marker)
            out.extend(data[i : i + length])
            i += length
            out.extend(data[i:])  # everything to EOI, inclusive
            break

        if i + 2 > n:
            break
        length = _read_u16_be(data, i)
        if length < 2 or i + length > n:
            break
        seg_start = i
        seg_end = i + length
        payload = data[i + 2 : seg_end]
        i = seg_end

        decision = _classify(marker, payload, aggressive=aggressive)
        if decision is None:
            out.append(0xff)
            out.append(marker)
            out.extend(data[seg_start:seg_end])
            continue

        removed.extend(decision)

    return StripResult(payload=bytes(out), removed=removed)


def _classify(marker: int, payload: bytes, *,
              aggressive: bool) -> list[FieldRemoved] | None:
    """Return a list of removed fields, or ``None`` to keep the segment."""
    if marker in _KEEP_ALWAYS:
        return None

    # APP1 (FFE1): EXIF or XMP.
    if marker == 0xe1:
        if payload.startswith(b"Exif\x00\x00"):
            return _explode_exif(payload[6:])
        if payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
            return [FieldRemoved("XMP",
                                 f"XMP packet, {len(payload)} bytes")]
        return [FieldRemoved("APP1", f"{len(payload)} bytes")]

    # APP13 (FFED): Photoshop Image Resources, typically holds IPTC.
    if marker == 0xed:
        if payload.startswith(b"Photoshop 3.0\x00"):
            return [FieldRemoved("IPTC",
                                 f"Photoshop resources, {len(payload)} bytes")]
        return [FieldRemoved("APP13", f"{len(payload)} bytes")]

    # COM (FFFE): comment.
    if marker == 0xfe:
        try:
            txt = payload.decode("utf-8", errors="replace")
        except Exception:
            txt = f"({len(payload)} bytes)"
        return [FieldRemoved("COM", txt[:60])]

    # APP14 (FFEE): Adobe tag - authoring hint.
    if marker == 0xee:
        if aggressive and payload.startswith(b"Adobe\x00"):
            return [FieldRemoved("Adobe.APP14", "authoring tag")]
        if aggressive:
            return [FieldRemoved("APP14", f"{len(payload)} bytes")]
        return None  # kept by default (some JPEGs rely on its colour-transform byte)

    # APP2 (FFE2): commonly ICC_PROFILE or MPF.
    if marker == 0xe2:
        if payload.startswith(b"ICC_PROFILE\x00"):
            if aggressive:
                return [FieldRemoved("ICC.Profile",
                                     f"{len(payload)} byte profile")]
            return None
        return [FieldRemoved("APP2", f"{len(payload)} bytes")]

    # APP3..APP12, APP15: vendor metadata.
    if 0xe3 <= marker <= 0xec or marker == 0xef:
        return [FieldRemoved(f"APP{marker - 0xe0}",
                             f"{len(payload)} bytes")]

    return None


# ---------------------------------------------------------------------------
# EXIF TIFF parser -- just enough to name identity-relevant fields.
# ---------------------------------------------------------------------------

_IFD0_TAGS = {
    0x010f: "Make",
    0x0110: "Model",
    0x0131: "Software",
    0x0132: "DateTime",
    0x013b: "Artist",
    0x8298: "Copyright",
    0x013e: "WhitePoint",
    0x013c: "HostComputer",
}

_EXIF_IFD_TAGS = {
    0x9003: "DateTimeOriginal",
    0x9004: "DateTimeDigitized",
    0xa430: "CameraOwnerName",
    0xa431: "BodySerialNumber",
    0xa432: "LensSpecification",
    0xa433: "LensMake",
    0xa434: "LensModel",
    0xa435: "LensSerialNumber",
    0x9286: "UserComment",
}

_GPS_IFD_TAGS = {
    0x0000: "GPSVersionID",
    0x0001: "GPSLatitudeRef",
    0x0002: "GPSLatitude",
    0x0003: "GPSLongitudeRef",
    0x0004: "GPSLongitude",
    0x0005: "GPSAltitudeRef",
    0x0006: "GPSAltitude",
    0x001d: "GPSDateStamp",
}

_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 10: 8}


def _explode_exif(tiff: bytes) -> list[FieldRemoved]:
    """Parse the embedded TIFF and emit one ``FieldRemoved`` per known tag.

    Always returns at least one row (a summary) even when parsing
    fails -- callers care that EXIF was removed, even if the
    structure was malformed.
    """
    if len(tiff) < 8:
        return [FieldRemoved("EXIF", f"{len(tiff)} bytes (malformed)")]

    bom = tiff[:2]
    if bom == b"II":
        endian = "<"
    elif bom == b"MM":
        endian = ">"
    else:
        return [FieldRemoved("EXIF", f"{len(tiff)} bytes (unknown byte order)")]

    try:
        magic, ifd0_off = struct.unpack_from(endian + "HI", tiff, 2)
    except struct.error:
        return [FieldRemoved("EXIF", f"{len(tiff)} bytes (header truncated)")]
    if magic != 0x002a:
        return [FieldRemoved("EXIF", f"{len(tiff)} bytes (bad magic)")]

    rows: list[FieldRemoved] = []
    seen: set[int] = set()  # guard against IFD cycles in malformed files

    def visit(offset: int, name_map: dict[int, str], prefix: str,
              follow_pointers: bool) -> None:
        if offset in seen or offset + 2 > len(tiff):
            return
        seen.add(offset)
        try:
            count = struct.unpack_from(endian + "H", tiff, offset)[0]
        except struct.error:
            return
        entries_start = offset + 2
        for k in range(count):
            entry_off = entries_start + k * 12
            if entry_off + 12 > len(tiff):
                break
            try:
                tag, ttype, tcount, tvalue = struct.unpack_from(
                    endian + "HHII", tiff, entry_off
                )
            except struct.error:
                break

            if follow_pointers and tag == 0x8769:  # ExifIFD pointer
                visit(tvalue, _EXIF_IFD_TAGS, "EXIF.", follow_pointers=False)
                continue
            if follow_pointers and tag == 0x8825:  # GPSIFD pointer
                visit(tvalue, _GPS_IFD_TAGS, "GPS.", follow_pointers=False)
                continue

            label = name_map.get(tag)
            if label is None:
                continue
            value = _read_value(tiff, endian, entry_off + 8, ttype, tcount)
            rows.append(FieldRemoved(f"{prefix}{label}", value))

    visit(ifd0_off, _IFD0_TAGS, "EXIF.", follow_pointers=True)

    # Fill in (not present) rows for every known tag we did NOT see,
    # so the user can answer "does this photo have X?" by scanning the
    # full schema. The UI's `[ Show: non-empty ]` toggle hides these
    # when the user only wants signal.
    seen_names: set[str] = {row.field for row in rows}
    for label in _IFD0_TAGS.values():
        full = f"EXIF.{label}"
        if full not in seen_names:
            rows.append(FieldRemoved(full, "(not present)"))
    for label in _EXIF_IFD_TAGS.values():
        full = f"EXIF.{label}"
        if full not in seen_names:
            rows.append(FieldRemoved(full, "(not present)"))
    for label in _GPS_IFD_TAGS.values():
        full = f"GPS.{label}"
        if full not in seen_names:
            rows.append(FieldRemoved(full, "(not present)"))

    return rows


def _read_value(tiff: bytes, endian: str, value_field_off: int,
                ttype: int, tcount: int) -> str:
    size = _TYPE_SIZES.get(ttype, 1) * tcount
    if size <= 4:
        data = tiff[value_field_off : value_field_off + size]
    else:
        try:
            off = struct.unpack_from(endian + "I", tiff, value_field_off)[0]
        except struct.error:
            return "(unreadable)"
        if off + size > len(tiff):
            return "(out of bounds)"
        data = tiff[off : off + size]

    if ttype == 2:  # ASCII
        return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    if ttype == 3:  # SHORT
        try:
            vals = struct.unpack(endian + ("H" * tcount), data[: 2 * tcount])
        except struct.error:
            return "(unreadable)"
        return ", ".join(str(v) for v in vals)
    if ttype == 4:  # LONG
        try:
            vals = struct.unpack(endian + ("I" * tcount), data[: 4 * tcount])
        except struct.error:
            return "(unreadable)"
        return ", ".join(str(v) for v in vals)
    if ttype == 5:  # RATIONAL
        parts: list[str] = []
        for j in range(tcount):
            chunk = data[j * 8 : j * 8 + 8]
            if len(chunk) < 8:
                break
            num, den = struct.unpack(endian + "II", chunk)
            if den == 0:
                parts.append("?")
            else:
                parts.append(f"{num / den:.6f}".rstrip("0").rstrip("."))
        return ", ".join(parts) if parts else "(unreadable)"
    return data.hex()[:60]


__all__ = ["strip_jpeg"]
