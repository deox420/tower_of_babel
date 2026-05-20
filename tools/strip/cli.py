"""STRIP CLI -- the primary user surface.

Argv shapes documented in ``docs/tools/STRIP.md`` Section 4. The
TUI screen in ``tools.strip.app`` is a thin wrapper around the
same pipeline.

Exit codes (from the doc):

    0  all files processed cleanly
    1  at least one file had unsupported format
    2  invocation error
    3  I/O error
    4  encrypted PDF or otherwise locked input
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from babel import theme
from shared.ui.compact import is_compact
from shared.ui.diff_view import render_diff
from tools.strip.core.pdf import EncryptedPDFError
from tools.strip.pipeline import (
    SUPPORTED_EXTENSIONS, FileOutcome,
    batch_dst, iter_batch, strip_path, stripper_for,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="babel strip",
        description="metadata laundry -- strips EXIF, XMP, IPTC, "
                    "Office properties, PDF /Info + XMP, ID3 tags.",
    )
    p.add_argument("path", nargs="?",
                   help="input file or directory")
    p.add_argument("-o", "--output",
                   help="explicit output path (single-file mode)")
    p.add_argument("-i", "--in-place", action="store_true",
                   help="overwrite the input file")
    p.add_argument("--batch", action="store_true",
                   help="treat path as a directory; recurse")
    p.add_argument("--aggressive", action="store_true",
                   help="also strip ICC profiles, rsids, software-version hints")
    p.add_argument("--hash-rename", action="store_true",
                   help="rename output to sha256(payload).<ext>")
    p.add_argument("--quiet", action="store_true",
                   help="suppress diff tables; still print summaries")
    p.add_argument("--json", action="store_true",
                   help="emit results as JSON (one record per file)")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would be removed, write nothing")
    p.add_argument("--setup", action="store_true",
                   help="diagnostic: show which formats are supported here")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.setup:
        return _run_setup()

    if args.path is None:
        return _run_interactive()

    if args.batch and args.in_place:
        sys.stderr.write("strip: --batch and --in-place are mutually exclusive\n")
        return 2
    if args.batch and args.output:
        sys.stderr.write("strip: --batch and --output are mutually exclusive "
                         "(use a directory output instead)\n")
        return 2
    if args.in_place and args.output:
        sys.stderr.write("strip: --in-place and --output are mutually exclusive\n")
        return 2
    if args.hash_rename and args.in_place:
        sys.stderr.write("strip: --hash-rename and --in-place are mutually exclusive\n")
        return 2

    path = Path(args.path)
    if not path.exists():
        sys.stderr.write(f"strip: no such path: {path}\n")
        return 2

    if args.batch:
        return _run_batch(path, args)
    return _run_single(path, args)


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def _run_single(path: Path, args: argparse.Namespace) -> int:
    if not path.is_file():
        sys.stderr.write(f"strip: not a file (use --batch for directories): {path}\n")
        return 2

    output = Path(args.output) if args.output else None
    try:
        outcome = strip_path(
            path,
            aggressive=args.aggressive,
            dry_run=args.dry_run,
            output=output,
            in_place=args.in_place,
            hash_rename=args.hash_rename,
        )
    except EncryptedPDFError as e:
        sys.stderr.write(f"strip: {e}\n")
        return 4

    if args.json:
        sys.stdout.write(json.dumps(_outcome_to_json(outcome), indent=2))
        sys.stdout.write("\n")
        return _exit_code([outcome])

    _emit_outcome(outcome, quiet=args.quiet, dry_run=args.dry_run)
    return _exit_code([outcome])


def _run_batch(path: Path, args: argparse.Namespace) -> int:
    if not path.is_dir():
        sys.stderr.write(f"strip: --batch needs a directory: {path}\n")
        return 2

    out_root = path.parent / f"{path.name}.stripped"
    if args.dry_run:
        # No directory created in dry-run; the planned dst paths still
        # render based on this root.
        pass
    else:
        try:
            out_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            sys.stderr.write(f"strip: cannot create {out_root}: {e}\n")
            return 3

    outcomes: list[FileOutcome] = []
    json_records: list[dict] = []

    for src in iter_batch(path):
        fn = stripper_for(src)
        if fn is None:
            outcomes.append(FileOutcome(src=src, dst=None, result=None,
                                        error=f"unsupported: {src.suffix}"))
            continue

        try:
            data = src.read_bytes()
        except OSError as e:
            outcomes.append(FileOutcome(src=src, dst=None, result=None,
                                        error=f"read failed: {e}"))
            continue

        size_before = len(data)
        try:
            result = fn(data, aggressive=args.aggressive)
        except EncryptedPDFError as e:
            outcomes.append(FileOutcome(src=src, dst=None, result=None,
                                        error=str(e), size_before=size_before))
            continue
        except Exception as e:
            outcomes.append(FileOutcome(
                src=src, dst=None, result=None,
                error=f"{type(e).__name__}: {e}",
                size_before=size_before))
            continue

        dst = batch_dst(src, path, out_root,
                        hash_rename=args.hash_rename, payload=result.payload)

        if not args.dry_run:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(result.payload)
            except OSError as e:
                outcomes.append(FileOutcome(
                    src=src, dst=dst, result=result,
                    error=f"write failed: {e}",
                    size_before=size_before,
                    size_after=len(result.payload)))
                continue

        outcomes.append(FileOutcome(
            src=src, dst=dst, result=result,
            size_before=size_before,
            size_after=len(result.payload),
        ))

    if args.json:
        for o in outcomes:
            json_records.append(_outcome_to_json(o))
        sys.stdout.write(json.dumps(json_records, indent=2))
        sys.stdout.write("\n")
        return _exit_code(outcomes)

    sep = theme.glyph("hbar_light") * 60
    for o in outcomes:
        sys.stdout.write(sep + "\n")
        _emit_outcome(o, quiet=args.quiet, dry_run=args.dry_run)
    sys.stdout.write(sep + "\n")
    n_ok = sum(1 for o in outcomes if o.error is None)
    n_err = sum(1 for o in outcomes if o.error is not None)
    sys.stdout.write(
        f" batch: {len(outcomes)} files, {n_ok} stripped, {n_err} errors\n"
    )
    if not args.dry_run:
        sys.stdout.write(f" output: {out_root}\n")
    return _exit_code(outcomes)


def _run_interactive() -> int:
    """Removed in v2.0.0 — interactive STRIP is reached via `babel`."""
    sys.stderr.write(
        "strip: interactive STRIP is now part of the babel menu in v2.0.0.\n"
        "       run `babel` and pick `[3] STRIP`, or use "
        "`babel --exec strip <file>` for one-shot scripting.\n"
    )
    return 2


def _run_setup() -> int:
    from tools.strip.setup_check import run as setup_run
    code, lines = setup_run()
    for line in lines:
        sys.stdout.write(line + "\n")
    return code


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _emit_outcome(o: FileOutcome, *, quiet: bool, dry_run: bool) -> None:
    if o.error:
        sys.stderr.write(f" {o.src}: ERROR {o.error}\n")
        return

    sys.stdout.write(f" {o.src.name}\n")
    if o.result is None:
        return
    if not quiet:
        sys.stdout.write(render_diff(o.result.removed,
                                     compact=is_compact()) + "\n")
    elif o.result.removed:
        sys.stdout.write(f"  {len(o.result.removed)} fields removed.\n")

    verb = "would write" if dry_run else "written to"
    if o.dst is not None:
        sys.stdout.write(f"  size {o.size_before} -> {o.size_after}  "
                         f"{verb} {o.dst}\n")


def _outcome_to_json(o: FileOutcome) -> dict:
    if o.error:
        return {
            "src": str(o.src),
            "error": o.error,
        }
    return {
        "src": str(o.src),
        "dst": str(o.dst) if o.dst else None,
        "size_before": o.size_before,
        "size_after": o.size_after,
        "removed": [
            {"field": r.field, "before": r.before, "after": r.after}
            for r in (o.result.removed if o.result else [])
        ],
    }


def _exit_code(outcomes: list[FileOutcome]) -> int:
    if not outcomes:
        return 0
    if any(o.error and "encrypted" in o.error.lower() for o in outcomes):
        return 4
    if any(o.error and "unsupported" in o.error.lower() for o in outcomes):
        return 1
    if any(o.error for o in outcomes):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
