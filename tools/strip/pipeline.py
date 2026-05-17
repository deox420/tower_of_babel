"""STRIP orchestration -- dispatch by extension, batch loop, writer.

The core strippers in ``tools.strip.core`` are pure functions on
bytes. This module adds the I/O: pick a stripper based on file
extension, write the result, optionally hash-rename, optionally
walk a directory.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from tools.strip.core import (
    strip_jpeg, strip_png, strip_pdf, strip_docx, strip_mp3,
)
from tools.strip.diff import StripResult


SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg",
    ".png",
    ".pdf",
    ".docx",
    ".mp3",
}


def stripper_for(path: Path) -> Callable[..., StripResult] | None:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return strip_jpeg
    if ext == ".png":
        return strip_png
    if ext == ".pdf":
        return strip_pdf
    if ext == ".docx":
        return strip_docx
    if ext == ".mp3":
        return strip_mp3
    return None


@dataclass(slots=True)
class FileOutcome:
    src: Path
    dst: Path | None
    result: StripResult | None
    error: str | None = None
    size_before: int = 0
    size_after: int = 0


def strip_path(
    src: Path,
    *,
    aggressive: bool = False,
    dry_run: bool = False,
    output: Path | None = None,
    in_place: bool = False,
    hash_rename: bool = False,
) -> FileOutcome:
    """Strip a single file. Never raises -- errors land in ``FileOutcome.error``.

    ``output``, ``in_place``, and the default (``<stem>.stripped<ext>``
    next to the source) are mutually exclusive; the caller is
    responsible for not setting more than one. ``dry_run`` skips the
    write but still returns the planned ``dst``.
    """
    if not src.exists() or not src.is_file():
        return FileOutcome(src=src, dst=None, result=None,
                           error=f"not a file: {src}")

    fn = stripper_for(src)
    if fn is None:
        return FileOutcome(src=src, dst=None, result=None,
                           error=f"unsupported extension: {src.suffix}")

    try:
        data = src.read_bytes()
    except OSError as e:
        return FileOutcome(src=src, dst=None, result=None,
                           error=f"read failed: {e}")
    size_before = len(data)

    try:
        result = fn(data, aggressive=aggressive)
    except Exception as e:
        return FileOutcome(src=src, dst=None, result=None,
                           error=f"{type(e).__name__}: {e}",
                           size_before=size_before)

    dst = _resolve_dst(src, output=output, in_place=in_place,
                       hash_rename=hash_rename, payload=result.payload)

    if not dry_run:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(result.payload)
        except OSError as e:
            return FileOutcome(src=src, dst=dst, result=result,
                               error=f"write failed: {e}",
                               size_before=size_before,
                               size_after=len(result.payload))

    return FileOutcome(
        src=src, dst=dst, result=result,
        size_before=size_before, size_after=len(result.payload),
    )


def _resolve_dst(src: Path, *, output: Path | None, in_place: bool,
                 hash_rename: bool, payload: bytes) -> Path:
    if in_place:
        return src
    if output is not None:
        return output
    if hash_rename:
        digest = hashlib.sha256(payload).hexdigest()
        return src.with_name(f"{digest}{src.suffix.lower()}")
    return src.with_name(f"{src.stem}.stripped{src.suffix.lower()}")


def iter_batch(src_dir: Path) -> Iterator[Path]:
    """Yield every supported file under ``src_dir`` (recursive, sorted)."""
    if not src_dir.is_dir():
        return
    for root, _dirs, files in os.walk(src_dir):
        for name in sorted(files):
            p = Path(root) / name
            if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield p


def batch_dst(src: Path, src_root: Path, out_root: Path, *,
              hash_rename: bool = False, payload: bytes = b"") -> Path:
    """Compute the output path for a file inside a batch run."""
    rel = src.relative_to(src_root)
    if hash_rename:
        digest = hashlib.sha256(payload).hexdigest()
        return out_root / rel.parent / f"{digest}{src.suffix.lower()}"
    return out_root / rel.parent / f"{src.stem}.stripped{src.suffix.lower()}"


__all__ = [
    "SUPPORTED_EXTENSIONS", "stripper_for",
    "FileOutcome", "strip_path", "iter_batch", "batch_dst",
]
