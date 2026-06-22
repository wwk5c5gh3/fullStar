#!/usr/bin/env bash
# install.sh — one-line installer for lockmac (macOS privacy veil).
#
#   Local:   ./install.sh            # run from inside the lockmac/ directory
#   Remote:  curl -fsSL <raw-url>/install.sh | bash   # clones then installs
#
# Does: check macOS + python3(>=3.9) + swiftc → pip install → precompile the
# Swift overlay → print next steps. lockmac has NO third-party Python deps.
set -euo pipefail

if [[ -t 1 ]]; then
  B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; D=$'\033[2m'; X=$'\033[0m'
else B=""; G=""; Y=""; R=""; D=""; X=""; fi
say()  { echo "${B}${G}▸ $*${X}"; }
warn() { echo "${Y}⚠ $*${X}" >&2; }
die()  { echo "${R}✗ $*${X}" >&2; exit 1; }

REPO_URL="${LOCKMAC_REPO:-https://github.com/wwk5c5gh3/fullStar.git}"

echo "${B}lockmac installer${X}"

# 0. platform + deps
[[ "$(uname -s)" == "Darwin" ]] || die "lockmac is macOS-only"
command -v python3 >/dev/null 2>&1 || die "python3 not found (install Python ≥3.9)"
PYVER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
python3 -c 'import sys;sys.exit(0 if sys.version_info[:2]>=(3,9) else 1)' \
  || die "python3 $PYVER too old — need ≥3.9"
say "python3 $PYVER"
if ! command -v swiftc >/dev/null 2>&1; then
  warn "swiftc not found — installing Xcode Command Line Tools (a dialog may appear)…"
  xcode-select --install 2>/dev/null || true
  die "re-run install.sh after Xcode Command Line Tools finish installing"
fi
say "swiftc $(swiftc --version 2>/dev/null | head -1 | sed 's/Apple //')"

# 1. locate the package source (local dir, else clone)
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$SELF_DIR" && -f "$SELF_DIR/pyproject.toml" ]]; then
  PKG_DIR="$SELF_DIR"
  say "installing from local source: $PKG_DIR"
else
  TMP="$(mktemp -d)"
  say "cloning $REPO_URL → $TMP"
  git clone --depth 1 "$REPO_URL" "$TMP/repo" >/dev/null 2>&1 || die "git clone failed"
  PKG_DIR="$TMP/repo/lockmac"
  [[ -f "$PKG_DIR/pyproject.toml" ]] || die "lockmac/ not found in repo"
fi

# 2. install (pipx if present for isolation, else pip --user)
if command -v pipx >/dev/null 2>&1; then
  say "installing with pipx"
  pipx install --force "$PKG_DIR" >/dev/null 2>&1 || pipx install --force -e "$PKG_DIR"
else
  say "installing with pip (--user)"
  python3 -m pip install --user -e "$PKG_DIR" -q
fi

# 3. ensure CLI on PATH
if ! command -v lockmac >/dev/null 2>&1; then
  warn "lockmac not on PATH — add your Python user-base bin to PATH:"
  echo "  ${D}export PATH=\"\$(python3 -m site --user-base)/bin:\$PATH\"${X}"
fi

# 4. precompile the Swift overlay (so first run isn't slow)
say "precompiling overlay"
python3 - <<'PY' || warn "overlay precompile skipped (will compile on first run)"
from lockmac import core
core.ensure_built()
print("  ✓ built:", core.BIN)
PY

echo
echo "${B}${G}✓ lockmac installed${X}"
cat <<EOF

${B}Next:${X}
  lockmac setup        ${D}# set unlock password + login autostart${X}
  lockmac tg-setup     ${D}# bind a Telegram bot for remote /lock /unlock${X}
  lockmac on / off     ${D}# raise / dismiss the privacy veil${X}
EOF
