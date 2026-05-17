#!/usr/bin/env bash
# Reproducible build for VOID.
# Run inside Dockerfile.build for byte-for-byte identical output. Running
# outside the pinned container will produce a binary that works but may
# differ from the official SHA256SUMS.
set -euo pipefail

# Work from repo root so spec/source paths resolve consistently whether
# build.sh is invoked from packaging/, root, or inside the container.
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/../VERSION" ]; then
    cd "$HERE/.."          # called from packaging/
elif [ -f "$HERE/VERSION" ]; then
    cd "$HERE"             # called from repo root (Dockerfile.build flattens it)
fi

VERSION="$(cat VERSION | tr -d '\n')"
SDE_FILE="packaging/SOURCE_DATE_EPOCH"
[ -f "$SDE_FILE" ] || SDE_FILE="SOURCE_DATE_EPOCH"
export SOURCE_DATE_EPOCH="$(cat "$SDE_FILE" | tr -d '\n')"
export PYTHONHASHSEED=0
export PYTHONDONTWRITEBYTECODE=1
export TZ=UTC
export LC_ALL=C.UTF-8

PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

PYI="${PYI:-pyinstaller}"
DIST_DIR="dist"
BUILD_DIR="build"
# Clear previous outputs. Tolerate ${DIST_DIR} being a Docker bind-mount
# point (-v "$PWD/dist:/src/dist"): rmdir on a mount returns EBUSY, but we
# can still wipe its contents. Build then writes fresh artifacts into it.
rm -rf "${BUILD_DIR}"
if [ -d "${DIST_DIR}" ]; then
    find "${DIST_DIR}" -mindepth 1 -delete 2>/dev/null || true
else
    mkdir -p "${DIST_DIR}"
fi

echo "[void/build] VERSION=${VERSION}  SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}"
echo "[void/build] PLATFORM=${PLATFORM}-${ARCH}"

# spec files live in packaging/ (unless build.sh was flattened by Dockerfile.build,
# in which case they're alongside this script — try both).
SPEC_DIR="packaging"
[ -f "$SPEC_DIR/babel.spec" ] || SPEC_DIR="."
"${PYI}" --clean --noconfirm "$SPEC_DIR/void-server.spec"
"${PYI}" --clean --noconfirm "$SPEC_DIR/babel.spec"

# Find on-disk timestamps and clamp them.
find "${DIST_DIR}" -exec touch -d "@${SOURCE_DATE_EPOCH}" {} +

cd "${DIST_DIR}"
# Stable filename pattern. `babel` is the suite binary that contains
# every tool (VOID today, MASK/STRIP/CARRIER/MIRAGE as they ship);
# `void-server` keeps a separate, narrow binary for server-only
# deployments per MASTER.md Section 8.2.
for stem in babel void-server; do
    if [ -f "${stem}" ]; then
        mv "${stem}" "${stem}-${VERSION}-${PLATFORM}-${ARCH}"
    elif [ -f "${stem}.exe" ]; then
        mv "${stem}.exe" "${stem}-${VERSION}-${PLATFORM}-${ARCH}.exe"
    fi
done

# Deterministic SHA256SUMS, sorted by filename.
: > SHA256SUMS
for f in $(ls -1 | LC_ALL=C sort); do
    if [ "$f" != "SHA256SUMS" ] && [ "$f" != "SHA256SUMS.asc" ]; then
        sha256sum "$f" >> SHA256SUMS
    fi
done

echo "[void/build] SHA256SUMS:"
cat SHA256SUMS

if [ "${VOID_GPG_SIGN:-0}" = "1" ]; then
    gpg --batch --yes --detach-sign --armor SHA256SUMS
    echo "[void/build] signed → dist/SHA256SUMS.asc"
fi
