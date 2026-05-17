"""PNG metadata stripper -- chunk-level walker, stdlib only.

PNG = 8-byte signature + sequence of chunks. Each chunk is
``length(4) | type(4) | data(length) | crc(4)``, all big-endian.
We re-emit critical chunks and a small set of ancillary chunks
that carry colour information; the rest are dropped and named.

Aggressive mode additionally drops ``iCCP`` (ICC profile) and
``sRGB`` rendering-intent hint.
"""
from __future__ import annotations

import struct

from shared.ui.diff_view import FieldRemoved
from tools.strip.diff import StripResult

_SIG = b"\x89PNG\r\n\x1a\n"

# Chunks we always preserve. Anything else is metadata or candidate metadata.
_KEEP_BASE = {
    b"IHDR", b"IDAT", b"IEND", b"PLTE", b"tRNS",
    b"gAMA", b"cHRM", b"bKGD", b"pHYs", b"sBIT", b"hIST",
    b"acTL", b"fcTL", b"fdAT",  # APNG
}
# Chunks kept by default but dropped in aggressive mode.
_KEEP_NON_AGGRESSIVE = {b"iCCP", b"sRGB"}


def strip_png(data: bytes, *, aggressive: bool = False) -> StripResult:
    if not data.startswith(_SIG):
        raise ValueError("not a PNG (signature mismatch)")

    out = bytearray(_SIG)
    removed: list[FieldRemoved] = []

    i = len(_SIG)
    n = len(data)
    while i + 8 <= n:
        length = struct.unpack_from(">I", data, i)[0]
        ctype = data[i + 4 : i + 8]
        chunk_end = i + 8 + length + 4  # +4 for trailing CRC
        if chunk_end > n:
            break
        chunk_bytes = data[i:chunk_end]
        payload = data[i + 8 : i + 8 + length]

        keep = ctype in _KEEP_BASE or (
            ctype in _KEEP_NON_AGGRESSIVE and not aggressive
        )

        if keep:
            out.extend(chunk_bytes)
        else:
            row = _name_png_chunk(ctype, payload)
            if row is not None:
                removed.append(row)

        i = chunk_end
        if ctype == b"IEND":
            break

    return StripResult(payload=bytes(out), removed=removed)


def _name_png_chunk(ctype: bytes, payload: bytes) -> FieldRemoved | None:
    name = ctype.decode("ascii", errors="replace")

    if ctype == b"tEXt":
        # NUL-separated keyword + text, Latin-1.
        try:
            kw, txt = payload.split(b"\x00", 1)
            return FieldRemoved(f"PNG.tEXt.{kw.decode('latin-1')}",
                                txt.decode('latin-1', errors='replace')[:80])
        except ValueError:
            return FieldRemoved("PNG.tEXt", f"{len(payload)} bytes")

    if ctype == b"iTXt":
        # keyword\0 compflag(1) compmethod(1) langtag\0 transkw\0 text
        parts = payload.split(b"\x00", 4)
        if len(parts) >= 5:
            kw = parts[0].decode("utf-8", errors="replace")
            txt = parts[4]
            # If compflag was set, text is zlib-compressed; we don't need to
            # decompress to *name* the field -- we only need a summary.
            return FieldRemoved(f"PNG.iTXt.{kw}",
                                f"{len(txt)} bytes (international)")
        return FieldRemoved("PNG.iTXt", f"{len(payload)} bytes")

    if ctype == b"zTXt":
        try:
            kw, _rest = payload.split(b"\x00", 1)
            return FieldRemoved(f"PNG.zTXt.{kw.decode('latin-1')}",
                                "compressed text")
        except ValueError:
            return FieldRemoved("PNG.zTXt", f"{len(payload)} bytes")

    if ctype == b"tIME":
        # 7 bytes: year(2) + month + day + hour + minute + second
        if len(payload) == 7:
            y = struct.unpack_from(">H", payload, 0)[0]
            mo, d, h, mi, s = payload[2:7]
            return FieldRemoved("PNG.tIME",
                                f"{y:04d}-{mo:02d}-{d:02d} "
                                f"{h:02d}:{mi:02d}:{s:02d}")
        return FieldRemoved("PNG.tIME", "(malformed)")

    if ctype == b"eXIf":
        return FieldRemoved("PNG.eXIf", f"EXIF block, {len(payload)} bytes")

    if ctype == b"iCCP":
        try:
            pname, _rest = payload.split(b"\x00", 1)
            return FieldRemoved("PNG.iCCP",
                                f"{pname.decode('latin-1', errors='replace')}, "
                                f"{len(payload)} bytes")
        except ValueError:
            return FieldRemoved("PNG.iCCP", f"{len(payload)} bytes")

    if ctype == b"sRGB":
        return FieldRemoved("PNG.sRGB", "rendering intent")

    # Unknown ancillary chunk -- name it generically. Critical chunks have
    # an uppercase first byte; we kept those above, so anything here is safe
    # to drop.
    return FieldRemoved(f"PNG.{name}", f"{len(payload)} bytes")


__all__ = ["strip_png"]
