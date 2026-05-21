"""MP3 metadata stripper -- ID3v2, ID3v1, and APEv2, byte-level.

We strip whole tag blocks rather than rewriting frame contents:
the diff lists what was inside the ID3v2 tag (TPE1=artist, TIT2=
title, ...) but the output payload has the entire tag removed.

Aggressive mode is a no-op here; the default already removes
everything tag-shaped.
"""
from __future__ import annotations

import struct

from shared.ui.diff_view import FieldRemoved
from tools.strip.diff import StripResult


_ID3V2_FRAME_LABELS = {
    # Most common identity-relevant frames in v2.3 / v2.4.
    b"TIT2": "Title",
    b"TPE1": "Artist",
    b"TPE2": "Band",
    b"TALB": "Album",
    b"TCOM": "Composer",
    b"TCON": "Genre",
    b"TYER": "Year",
    b"TDRC": "RecordingTime",
    b"TRCK": "Track",
    b"COMM": "Comment",
    b"USLT": "Lyrics",
    b"TPOS": "PartOfSet",
    b"TCOP": "Copyright",
    b"TENC": "EncodedBy",
    b"TSSE": "EncodingSettings",
    b"TBPM": "BPM",
    b"APIC": "AttachedPicture",
    b"WXXX": "URL",
    b"PRIV": "Private",
    b"UFID": "UniqueFileID",
}


def strip_mp3(data: bytes, *, aggressive: bool = False) -> StripResult:
    removed: list[FieldRemoved] = []
    head_drop = 0
    tail_drop = 0

    # ID3v2 at start.
    if len(data) >= 10 and data[:3] == b"ID3":
        version = (data[3], data[4])
        size = _syncsafe(data[6:10])
        # +10 for the header itself; the optional footer (v2.4 with flag bit)
        # adds another 10 we'd need to drop, but we just drop the whole tag.
        flags = data[5]
        total = 10 + size + (10 if (flags & 0x10) else 0)
        if total <= len(data):
            head_drop = total
            removed.extend(_inspect_id3v2(data[:total], version))

    # ID3v1 at end (last 128 bytes).
    if len(data) - head_drop >= 128 and \
            data[-128:-125] == b"TAG":
        tail_drop = 128
        removed.extend(_inspect_id3v1(data[-128:]))

    # APEv2 -- can sit before an ID3v1 (so before tail_drop) or be the only
    # trailer. APE header/footer = "APETAGEX" + 8-byte version + 4-byte size
    # (excluding header) + 4-byte item-count + 4-byte flags + 8-byte reserved.
    ape_end = len(data) - tail_drop
    if ape_end >= 32 and data[ape_end - 32 : ape_end - 24] == b"APETAGEX":
        try:
            footer = data[ape_end - 32 : ape_end]
            ape_size = struct.unpack_from("<I", footer, 12)[0]
            ape_start = ape_end - ape_size - 32  # footer points past header
            if 0 <= ape_start <= ape_end - 32:
                ape_block_size = ape_end - ape_start
                tail_drop += ape_block_size
                removed.append(FieldRemoved(
                    "MP3.APE", f"APEv2 tag, {ape_block_size} bytes"))
        except struct.error:
            pass

    # `(not present)` rows for the standard frames that weren't in
    # the file (ID3v2 + the four ID3v1 string fields).
    seen_ids: set[str] = set()
    for row in removed:
        if row.field.startswith("MP3.ID3v2."):
            seen_ids.add(row.field[len("MP3.ID3v2."):])
        elif row.field.startswith("MP3.ID3v1."):
            seen_ids.add(f"v1:{row.field[len('MP3.ID3v1.'):]}")
    for label in _ID3V2_FRAME_LABELS.values():
        if label not in seen_ids:
            removed.append(FieldRemoved(
                f"MP3.ID3v2.{label}", "(not present)",
            ))
    for label in ("Title", "Artist", "Album", "Year"):
        if f"v1:{label}" not in seen_ids:
            removed.append(FieldRemoved(
                f"MP3.ID3v1.{label}", "(not present)",
            ))

    if head_drop == 0 and tail_drop == 0:
        return StripResult(payload=data, removed=removed)

    payload = data[head_drop : len(data) - tail_drop if tail_drop else None]
    return StripResult(payload=bytes(payload), removed=removed)


def _syncsafe(b: bytes) -> int:
    """ID3v2 syncsafe int: 4 bytes, each contributes 7 bits, MSB cleared."""
    if len(b) != 4:
        return 0
    return ((b[0] & 0x7f) << 21) | ((b[1] & 0x7f) << 14) | \
           ((b[2] & 0x7f) << 7) | (b[3] & 0x7f)


def _inspect_id3v2(block: bytes, version: tuple[int, int]) -> list[FieldRemoved]:
    out: list[FieldRemoved] = []
    out.append(FieldRemoved("MP3.ID3v2",
                            f"v2.{version[0]}.{version[1]}, "
                            f"{len(block)} bytes"))

    flags = block[5]
    pos = 10
    if flags & 0x40:  # extended header
        if version[0] == 4:
            try:
                ext_size = _syncsafe(block[10:14])
            except Exception:
                return out
            pos = 10 + ext_size
        else:
            try:
                ext_size = struct.unpack_from(">I", block, 10)[0]
            except struct.error:
                return out
            pos = 14 + ext_size

    while pos + 10 <= len(block):
        fid = block[pos : pos + 4]
        if fid == b"\x00\x00\x00\x00":
            break
        if version[0] == 4:
            fsize = _syncsafe(block[pos + 4 : pos + 8])
        else:
            try:
                fsize = struct.unpack_from(">I", block, pos + 4)[0]
            except struct.error:
                break
        if fsize <= 0 or pos + 10 + fsize > len(block):
            break
        body = block[pos + 10 : pos + 10 + fsize]
        label = _ID3V2_FRAME_LABELS.get(fid, fid.decode("latin-1", errors="replace"))
        out.append(FieldRemoved(f"MP3.ID3v2.{label}",
                                _summarise_id3v2_frame(fid, body)))
        pos += 10 + fsize

    return out


def _summarise_id3v2_frame(fid: bytes, body: bytes) -> str:
    if fid == b"APIC":
        return f"image, {len(body)} bytes"
    if fid == b"PRIV" or fid == b"UFID":
        return f"{len(body)} bytes binary"
    if fid.startswith(b"T") or fid == b"COMM" or fid == b"USLT" or fid == b"WXXX":
        # Text frames: 1 byte encoding + text (NUL-terminated for some).
        if not body:
            return ""
        enc = body[0]
        text = body[1:]
        try:
            if enc == 0:
                s = text.decode("latin-1", errors="replace")
            elif enc == 1:
                s = text.decode("utf-16", errors="replace")
            elif enc == 2:
                s = text.decode("utf-16-be", errors="replace")
            else:
                s = text.decode("utf-8", errors="replace")
        except Exception:
            s = ""
        return s.split("\x00", 1)[0][:80]
    return f"{len(body)} bytes"


def _inspect_id3v1(block: bytes) -> list[FieldRemoved]:
    if len(block) != 128 or block[:3] != b"TAG":
        return []
    out: list[FieldRemoved] = [FieldRemoved("MP3.ID3v1", "trailer, 128 bytes")]
    title = block[3:33].rstrip(b"\x00 ").decode("latin-1", errors="replace")
    artist = block[33:63].rstrip(b"\x00 ").decode("latin-1", errors="replace")
    album = block[63:93].rstrip(b"\x00 ").decode("latin-1", errors="replace")
    year = block[93:97].rstrip(b"\x00 ").decode("latin-1", errors="replace")
    if title:
        out.append(FieldRemoved("MP3.ID3v1.Title", title))
    if artist:
        out.append(FieldRemoved("MP3.ID3v1.Artist", artist))
    if album:
        out.append(FieldRemoved("MP3.ID3v1.Album", album))
    if year:
        out.append(FieldRemoved("MP3.ID3v1.Year", year))
    return out


__all__ = ["strip_mp3"]
