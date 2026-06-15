"""CARRIER CLI front-end.

Subcommands::

    babel carrier embed <cover> <payload> [-o <out>]
    babel carrier extract <stego> [-o <out>]
    babel carrier capacity <cover>
    babel carrier inspect <cover>
    babel carrier --setup

Passphrase is read from ``BABEL_CARRIER_PASS`` if set, otherwise
prompted on stdin with masking when a TTY is attached. Exit codes
follow ``docs/tools/CARRIER.md`` Section 4.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from cryptography.exceptions import InvalidTag

from shared.ui.hex_view import render_hex
from tools.carrier.capacity import PayloadTooLargeError
from tools.carrier.chisquare import chi_square
from tools.carrier.pipeline import (
    LSB_EMBEDDED_THRESHOLD, KdfParams, TamperedCoverError,
    UnsupportedCoverError, detect_format, embed_payload, extract_payload,
)
from tools.carrier.core import png as png_core
from tools.carrier.core import wav as wav_core


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="babel carrier",
        description="steganography -- hide an encrypted payload in a PNG or WAV",
    )
    p.add_argument("--setup", action="store_true",
                   help="diagnostic: show which cover formats are supported")
    sub = p.add_subparsers(dest="cmd")

    common_kdf = argparse.ArgumentParser(add_help=False)
    common_kdf.add_argument("--time-cost", type=int, default=None,
                            help="Argon2id time cost (default 3)")
    common_kdf.add_argument("--memory-cost", type=int, default=None,
                            help="Argon2id memory cost in KiB (default 65536)")
    common_kdf.add_argument("--parallelism", type=int, default=None,
                            help="Argon2id parallelism (default 4)")

    p_embed = sub.add_parser("embed", parents=[common_kdf],
                             help="embed a payload into a cover")
    p_embed.add_argument("cover")
    p_embed.add_argument("payload")
    p_embed.add_argument("-o", "--output")
    p_embed.add_argument("--strict", action="store_true",
                         help="refuse to embed into a cover that fails chi-square")
    p_embed.add_argument("--no-compress", action="store_true",
                         help="skip the zlib pre-pass")
    p_embed.add_argument("--json", action="store_true")

    p_extract = sub.add_parser("extract", parents=[common_kdf],
                               help="extract a payload from a stego cover")
    p_extract.add_argument("stego")
    p_extract.add_argument("-o", "--output")
    p_extract.add_argument("--no-compress", action="store_true",
                           help="payload was embedded with --no-compress")
    p_extract.add_argument("--json", action="store_true")

    p_capacity = sub.add_parser("capacity",
                                help="report the safe-capacity of a cover")
    p_capacity.add_argument("cover")
    p_capacity.add_argument("--json", action="store_true")

    p_inspect = sub.add_parser("inspect",
                               help="run the chi-square LSB tampering check")
    p_inspect.add_argument("cover")
    p_inspect.add_argument("--json", action="store_true")

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.setup:
        from tools.carrier.setup_check import run as setup_run
        code, lines = setup_run()
        for line in lines:
            sys.stdout.write(line + "\n")
        return code

    if args.cmd is None:
        return _run_interactive()

    if args.cmd == "embed":
        return _cmd_embed(args)
    if args.cmd == "extract":
        return _cmd_extract(args)
    if args.cmd == "capacity":
        return _cmd_capacity(args)
    if args.cmd == "inspect":
        return _cmd_inspect(args)
    parser.print_help()
    return 2


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_embed(args: argparse.Namespace) -> int:
    cover_bytes = _read_file(args.cover)
    if cover_bytes is None:
        return 3
    payload_bytes = _read_file(args.payload)
    if payload_bytes is None:
        return 3

    passphrase = _read_passphrase(confirm=True)
    if passphrase is None:
        return 2

    kdf = _kdf_params_from_args(args)
    try:
        fmt = detect_format(cover_bytes)
    except UnsupportedCoverError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 4

    try:
        report = embed_payload(
            cover_bytes, payload_bytes, passphrase,
            fmt=fmt, kdf=kdf,
            compress=not args.no_compress,
            strict_chi2=args.strict,
        )
    except PayloadTooLargeError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 5
    except TamperedCoverError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 7
    except ValueError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 4

    out_path = Path(args.output) if args.output \
        else Path(args.cover).with_suffix(f".carrier{Path(args.cover).suffix}")
    try:
        out_path.write_bytes(report.output)
    except OSError as e:
        sys.stderr.write(f"carrier: write failed: {e}\n")
        return 3

    if args.json:
        sys.stdout.write(json.dumps({
            "format": fmt,
            "output": str(out_path),
            "capacity_bytes": report.capacity.safe_bytes,
            "channel_bits": report.capacity.channel_bits,
            "chi_square": {
                "chi2": report.chi_square.chi2,
                "df": report.chi_square.df,
                "p_value": report.chi_square.p_value,
            },
            "chi_square_warn": report.chi_square_warn,
            "payload_size": report.payload_size,
            "framed_size": report.framed_size,
            "compressed": report.compressed,
        }, indent=2) + "\n")
        return 0

    sys.stdout.write(f" cover         {args.cover}\n")
    sys.stdout.write(f" format        {fmt}\n")
    sys.stdout.write(f" capacity      {report.capacity.safe_bytes} bytes "
                     f"(of {report.capacity.channel_bits // 8} max)\n")
    sys.stdout.write(f" chi-square    chi2={report.chi_square.chi2:.2f} "
                     f"p={report.chi_square.p_value:.4f}"
                     f"{'  (warn: looks tampered)' if report.chi_square_warn else ''}\n")
    sys.stdout.write(f" payload       {report.payload_size} bytes "
                     f"(compressed: {report.compressed})\n")
    sys.stdout.write(f" framed        {report.framed_size} bytes embedded\n")
    sys.stdout.write(f" output        {out_path}\n")
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    stego_bytes = _read_file(args.stego)
    if stego_bytes is None:
        return 3

    passphrase = _read_passphrase(confirm=False)
    if passphrase is None:
        return 2

    kdf = _kdf_params_from_args(args)
    try:
        fmt = detect_format(stego_bytes)
    except UnsupportedCoverError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 4

    try:
        report = extract_payload(
            stego_bytes, passphrase,
            fmt=fmt, kdf=kdf, compress=not args.no_compress,
        )
    except InvalidTag:
        sys.stderr.write("carrier: wrong passphrase or no payload here\n")
        return 6
    except ValueError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 4

    out_path = Path(args.output) if args.output else None

    if args.json:
        sys.stdout.write(json.dumps({
            "format": fmt,
            "output": str(out_path) if out_path else None,
            "size": len(report.payload),
            "compressed": report.compressed,
            "preview_hex": report.payload[:64].hex(),
        }, indent=2) + "\n")
        if out_path:
            try:
                out_path.write_bytes(report.payload)
            except OSError as e:
                sys.stderr.write(f"carrier: write failed: {e}\n")
                return 3
        return 0

    if out_path is not None:
        try:
            out_path.write_bytes(report.payload)
        except OSError as e:
            sys.stderr.write(f"carrier: write failed: {e}\n")
            return 3
        sys.stdout.write(f"extracted {len(report.payload)} bytes to {out_path}\n")
        sys.stdout.write(render_hex(report.payload[:64], max_rows=4) + "\n")
        return 0

    sys.stdout.buffer.write(report.payload)
    return 0


def _cmd_capacity(args: argparse.Namespace) -> int:
    cover_bytes = _read_file(args.cover)
    if cover_bytes is None:
        return 3
    try:
        fmt = detect_format(cover_bytes)
    except UnsupportedCoverError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 4

    if fmt == "png":
        cov = png_core.open_cover(cover_bytes)
        cap = png_core.cover_capacity(cov)
        geom = f"{cov.width}x{cov.height}x{cov.n_channels} ({cov.mode})"
    else:
        cov = wav_core.open_cover(cover_bytes)
        cap = wav_core.cover_capacity(cov)
        geom = (f"{cov.n_frames} frames x {cov.n_channels}ch "
                f"@ {cov.frame_rate}Hz, {cov.sample_width * 8}-bit")

    if args.json:
        sys.stdout.write(json.dumps({
            "format": fmt,
            "geometry": geom,
            "channel_bits": cap.channel_bits,
            "safe_bytes": cap.safe_bytes,
            "safety_factor": cap.safety_factor,
        }, indent=2) + "\n")
        return 0

    sys.stdout.write(f" format        {fmt}\n")
    sys.stdout.write(f" geometry      {geom}\n")
    sys.stdout.write(f" channel bits  {cap.channel_bits}\n")
    sys.stdout.write(f" safe bytes    {cap.safe_bytes} "
                     f"(factor {cap.safety_factor:.3f})\n")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    cover_bytes = _read_file(args.cover)
    if cover_bytes is None:
        return 3
    try:
        fmt = detect_format(cover_bytes)
    except UnsupportedCoverError as e:
        sys.stderr.write(f"carrier: {e}\n")
        return 4

    if fmt == "png":
        cov = png_core.open_cover(cover_bytes)
        samples = png_core.lsb_samples(cov)
    else:
        cov = wav_core.open_cover(cover_bytes)
        samples = wav_core.lsb_samples(cov)

    res = chi_square(samples)
    looks_tampered = res.p_value > LSB_EMBEDDED_THRESHOLD

    if args.json:
        sys.stdout.write(json.dumps({
            "format": fmt,
            "chi2": res.chi2,
            "df": res.df,
            "p_value": res.p_value,
            "n_samples": res.n_samples,
            "looks_tampered": looks_tampered,
            "threshold": LSB_EMBEDDED_THRESHOLD,
        }, indent=2) + "\n")
        return 0

    verdict = "looks tampered" if looks_tampered else "looks untampered"
    sys.stdout.write(f" format        {fmt}\n")
    sys.stdout.write(f" samples       {res.n_samples}\n")
    sys.stdout.write(f" chi2          {res.chi2:.2f}  (df={res.df})\n")
    sys.stdout.write(f" p-value       {res.p_value:.4f}\n")
    sys.stdout.write(f" verdict       {verdict} "
                     f"(threshold p > {LSB_EMBEDDED_THRESHOLD})\n")
    return 0


def _run_interactive() -> int:
    """Removed in v2.0.0 — interactive CARRIER is reached via `babel`."""
    sys.stderr.write(
        "carrier: interactive CARRIER is now part of the babel menu in v2.0.0.\n"
        "         run `babel` and pick `[4] CARRIER`, or use "
        "`babel --exec carrier <op> ...` for one-shot scripting.\n"
    )
    return 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_file(path: str) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except OSError as e:
        sys.stderr.write(f"carrier: cannot read {path}: {e}\n")
        return None


def _read_passphrase(*, confirm: bool) -> bytes | None:
    env = os.environ.get("BABEL_CARRIER_PASS")
    if env is not None:
        return env.encode("utf-8")

    try:
        p1 = getpass.getpass("passphrase: ")
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\ncarrier: no passphrase\n")
        return None
    if not p1:
        sys.stderr.write("carrier: empty passphrase refused\n")
        return None
    if confirm:
        try:
            p2 = getpass.getpass("passphrase (confirm): ")
        except (EOFError, KeyboardInterrupt):
            sys.stderr.write("\ncarrier: no passphrase\n")
            return None
        if p1 != p2:
            sys.stderr.write("carrier: passphrases do not match\n")
            return None
    return p1.encode("utf-8")


def _kdf_params_from_args(args: argparse.Namespace) -> KdfParams:
    p = KdfParams()
    if getattr(args, "time_cost", None) is not None:
        p.time_cost = args.time_cost
    if getattr(args, "memory_cost", None) is not None:
        p.memory_cost = args.memory_cost
    if getattr(args, "parallelism", None) is not None:
        p.parallelism = args.parallelism
    return p


if __name__ == "__main__":
    raise SystemExit(main())
