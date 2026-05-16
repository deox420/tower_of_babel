#!/usr/bin/env bash
# VOID — one-command setup for Linux / macOS / Termux.
#
#   curl -sSL https://raw.githubusercontent.com/deox420/tower_of_babel/main/install.sh | bash
#
# After this script finishes you can run:
#   void                     # to join (paste a void://… invite)
#   void --make-invite       # to host (prints a void://… line)
#
# The script:
#   1. Detects the platform and package manager.
#   2. Installs python3 and tor (asks for sudo only if needed).
#   3. Drops a per-user torrc snippet enabling ControlPort 9051 + cookie auth.
#   4. Starts tor in the background and waits for SOCKS + control ports.
#   5. pip-installs VOID in user mode (no global pollution).
set -euo pipefail

C_GREEN=$'\033[1;32m'; C_CYAN=$'\033[1;36m'; C_RED=$'\033[1;31m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'

say()  { printf "%s[void]%s %s\n" "$C_CYAN" "$C_RST" "$*"; }
ok()   { printf "%s[ok]%s   %s\n" "$C_GREEN" "$C_RST" "$*"; }
warn() { printf "%s[!]%s    %s\n" "$C_RED"   "$C_RST" "$*" >&2; }
die()  { warn "$*"; exit 1; }

# ---------- detect platform ------------------------------------------------

UNAME=$(uname -s)
IS_TERMUX=0
IS_MAC=0
IS_LINUX=0
PKG=""
SUDO=""

case "$UNAME" in
    Linux*)
        if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then
            IS_TERMUX=1
            PKG="pkg"
        else
            IS_LINUX=1
            if command -v apt-get >/dev/null 2>&1; then PKG="apt"
            elif command -v dnf >/dev/null 2>&1; then PKG="dnf"
            elif command -v pacman >/dev/null 2>&1; then PKG="pacman"
            else PKG="unknown"
            fi
            if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
        fi
        ;;
    Darwin*)
        IS_MAC=1
        if command -v brew >/dev/null 2>&1; then PKG="brew"
        else die "Homebrew not found. Install it first: https://brew.sh"
        fi
        ;;
    *) die "Unsupported platform: $UNAME (Linux, macOS, or Termux only)" ;;
esac

say "platform: $UNAME ($PKG)"

# ---------- install python + tor -------------------------------------------

install_pkgs() {
    case "$PKG" in
        apt)    $SUDO apt-get update -qq && $SUDO apt-get install -y python3 python3-pip python3-venv tor git curl ;;
        dnf)    $SUDO dnf install -y python3 python3-pip tor git curl ;;
        pacman) $SUDO pacman -Sy --noconfirm python python-pip tor git curl ;;
        brew)   brew install python tor git ;;
        pkg)
            pkg update -y >/dev/null
            # Core deps with prebuilt Termux packages. cmake + libsodium are
            # needed below to compile the libxeddsa C library from source.
            pkg install -y python tor python-cryptography clang make cmake \
                          libffi libsodium git pkg-config openssl
            # pydantic-core is a Rust extension with no Android wheel on PyPI,
            # so pip would otherwise fail trying to fetch a rustup toolchain
            # for aarch64-linux-android (which doesn't exist). Termux's own
            # Rust package targets android-aarch64 natively.
            if ! python -c "import pydantic_core" 2>/dev/null; then
                say "installing Rust toolchain for pydantic-core (one-time, ~150 MB)..."
                pkg install -y rust binutils
            fi
            # libxeddsa C library — the Python 'xeddsa' wrapper links against
            # -lxeddsa and -lsodium at install time. Termux ships libsodium
            # but NOT libxeddsa, so we build it from source. Idempotent: skip
            # if the .so is already in $PREFIX/lib.
            if [ ! -f "$PREFIX/lib/libxeddsa.so" ] && [ ! -f "$PREFIX/lib/libxeddsa.a" ]; then
                # Try a package one more time in case Termux adds it later.
                pkg install -y libxeddsa 2>/dev/null || {
                    say "compiling libxeddsa from source (one-time, ~2 min)..."
                    local xed="$HOME/.cache/void-libxeddsa-src"
                    rm -rf "$xed"
                    git clone --depth 1 https://github.com/Syndace/libxeddsa.git "$xed"
                    mkdir -p "$xed/build"
                    (
                        cd "$xed/build"
                        cmake .. -DCMAKE_INSTALL_PREFIX="$PREFIX" \
                                 -DCMAKE_BUILD_TYPE=Release
                        make -j"$(nproc 2>/dev/null || echo 2)"
                        make install
                    ) || die "libxeddsa build failed — paste the output above"
                    rm -rf "$xed"
                    ok "libxeddsa installed at \$PREFIX/lib"
                }
            else
                ok "libxeddsa already present"
            fi
            ;;
        *)      die "Unknown package manager. Install python3 + tor manually, then re-run." ;;
    esac
}

say "installing python3 + tor + git..."
install_pkgs
ok "system deps installed"

# ---------- configure tor (per-user, no /etc edits) ------------------------

if [ "$IS_TERMUX" = "1" ]; then
    TORRC_DIR="$PREFIX/etc/tor"
    TORRC="$TORRC_DIR/torrc"
elif [ "$IS_MAC" = "1" ]; then
    # brew default location
    if [ -d /opt/homebrew/etc/tor ]; then
        TORRC_DIR=/opt/homebrew/etc/tor
    else
        TORRC_DIR=/usr/local/etc/tor
    fi
    TORRC="$TORRC_DIR/torrc"
else
    # Linux: use a per-user torrc launched directly. We do NOT touch /etc/tor.
    TORRC_DIR="$HOME/.config/void"
    TORRC="$TORRC_DIR/torrc"
    mkdir -p "$TORRC_DIR"
    chmod 700 "$TORRC_DIR"
fi

CONFIGURE_TORRC=1
if [ -f "$TORRC" ] && grep -qE '^[[:space:]]*ControlPort[[:space:]]+9051' "$TORRC"; then
    CONFIGURE_TORRC=0
fi

if [ "$CONFIGURE_TORRC" = "1" ]; then
    say "writing torrc with ControlPort 9051 + cookie auth → $TORRC"
    {
        echo "## VOID — added by install.sh"
        echo "ControlPort 9051"
        echo "CookieAuthentication 1"
        echo "CookieAuthFileGroupReadable 1"
        if [ "$IS_LINUX" = "1" ]; then
            echo "DataDirectory $HOME/.config/void/tor-data"
        fi
    } >> "$TORRC" 2>/dev/null || {
        # fall back to ~/.tor if we can't write the system torrc (macOS sandbox, etc.)
        TORRC_DIR="$HOME/.tor"
        TORRC="$TORRC_DIR/torrc"
        mkdir -p "$TORRC_DIR"
        {
            echo "## VOID — added by install.sh"
            echo "ControlPort 9051"
            echo "CookieAuthentication 1"
            echo "CookieAuthFileGroupReadable 1"
            echo "DataDirectory $HOME/.tor/data"
        } > "$TORRC"
    }
    ok "torrc configured"
else
    ok "existing torrc already has ControlPort"
fi

# ---------- start tor ------------------------------------------------------

start_tor() {
    if (echo > /dev/tcp/127.0.0.1/9050) 2>/dev/null; then
        return 0
    fi
    if [ "$IS_LINUX" = "1" ]; then
        # If system tor is installed and managed by systemd, try that first IF the
        # user has sudo. Otherwise, run as the current user with our own torrc.
        if command -v systemctl >/dev/null 2>&1 && [ -f /etc/tor/torrc ] && [ -n "$SUDO" ]; then
            $SUDO systemctl restart tor 2>/dev/null || tor -f "$TORRC" --runasdaemon 1 >/dev/null 2>&1 &
        else
            tor -f "$TORRC" --runasdaemon 1 >/dev/null 2>&1 &
        fi
    elif [ "$IS_MAC" = "1" ]; then
        brew services start tor >/dev/null 2>&1 || tor -f "$TORRC" --runasdaemon 1 >/dev/null 2>&1 &
    elif [ "$IS_TERMUX" = "1" ]; then
        (tor --quiet >/dev/null 2>&1 &)
    fi
}

say "starting tor (may take 10-30 s to build a circuit)..."
start_tor

for i in $(seq 1 60); do
    if (echo > /dev/tcp/127.0.0.1/9050) 2>/dev/null; then
        ok "Tor SOCKS5 up on 127.0.0.1:9050"
        break
    fi
    sleep 1
done

if ! (echo > /dev/tcp/127.0.0.1/9050) 2>/dev/null; then
    warn "Tor didn't come up automatically. Try starting it by hand: tor -f $TORRC"
fi

# ---------- install VOID ---------------------------------------------------

REPO_URL="https://github.com/deox420/tower_of_babel.git"
SRC_DIR="$HOME/.local/share/void"

say "fetching VOID source → $SRC_DIR"
if [ -d "$SRC_DIR/.git" ]; then
    git -C "$SRC_DIR" pull --quiet --ff-only || true
else
    mkdir -p "$(dirname "$SRC_DIR")"
    git clone --depth 1 "$REPO_URL" "$SRC_DIR" >/dev/null
fi

PIP_BREAK="--break-system-packages"
# Newer pip (Debian 12+) requires --break-system-packages for --user installs.
# Older pip rejects the flag; check support first.
if ! python3 -m pip install --help 2>/dev/null | grep -q break-system-packages; then
    PIP_BREAK=""
fi

if [ "$IS_TERMUX" = "1" ]; then
    # On Termux, pydantic-core compiles from source — visible progress matters.
    say "installing void-chat (Termux compiles pydantic-core from source, expect 3-8 min)..."
    python3 -m pip install --user $PIP_BREAK -e "$SRC_DIR"
else
    say "installing void-chat (pip --user)..."
    python3 -m pip install --quiet --user $PIP_BREAK -e "$SRC_DIR" >/dev/null
fi

# Make sure ~/.local/bin is on PATH for this session and future ones.
# Note: this script runs in a subshell when invoked via `curl | bash`, so the
# `export PATH=...` we set here doesn't reach the user's parent shell. We
# patch every RC file that exists so the next interactive session picks it
# up, and the final banner tells the user how to use 'void' RIGHT NOW.
BIN_DIR="$HOME/.local/bin"
NEEDS_PATH=1
case ":$PATH:" in
    *":$BIN_DIR:"*) NEEDS_PATH=0 ;;
esac

if [ "$NEEDS_PATH" = "1" ]; then
    export PATH="$BIN_DIR:$PATH"
    # Patch every shell rc file the user might use. .profile is the catch-all
    # because Termux + bash login shells often source it instead of .bashrc.
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile" "$HOME/.bash_profile"; do
        if [ -f "$rc" ] && ! grep -q 'HOME/.local/bin' "$rc" 2>/dev/null; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
        fi
    done
    # If none of them existed (fresh Termux), create .bashrc so it sticks.
    if [ ! -f "$HOME/.bashrc" ] && [ ! -f "$HOME/.profile" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' > "$HOME/.bashrc"
    fi
fi

# Sanity check: is 'void' callable as a command? If not (pip's entry-point
# generation failed, or PATH is being filtered), tell the user the module path.
VOID_BIN="$BIN_DIR/void"
if [ ! -x "$VOID_BIN" ]; then
    # Some Termux configurations install entry points to $PREFIX/bin instead.
    if [ -x "$PREFIX/bin/void" ] 2>/dev/null; then
        VOID_BIN="$PREFIX/bin/void"
    else
        VOID_BIN=""
    fi
fi

ok "void installed"

# ---------- summary --------------------------------------------------------

if [ "$NEEDS_PATH" = "1" ]; then
    PATH_NOTE="${C_DIM}(your current shell doesn't have ~/.local/bin in PATH yet — run${C_RST}
  ${C_DIM} 'source ~/.bashrc' OR open a new Termux session before typing 'void')${C_RST}"
else
    PATH_NOTE=""
fi

cat <<EOF

${C_GREEN}════════════════════════════════════════════════${C_RST}
  VOID is ready.

  ${C_CYAN}To host a room (you'll get a void:// link to share):${C_RST}
      void --make-invite

  ${C_CYAN}To join a room (paste the void:// link you received):${C_RST}
      void

  ${C_DIM}help inside the app:  press F1${C_RST}
  ${C_DIM}quick health check:   void --setup${C_RST}
  ${PATH_NOTE}
${C_GREEN}════════════════════════════════════════════════${C_RST}

EOF
