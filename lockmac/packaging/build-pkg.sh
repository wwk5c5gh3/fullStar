#!/usr/bin/env bash
# build-pkg.sh — build a double-clickable lockmac.pkg installer (macOS).
#
# Produces an UNSIGNED installer at dist/lockmac-<ver>.pkg that installs:
#   /usr/local/lib/lockmac/lockmac/   the Python package (zero third-party deps)
#   /usr/local/lib/lockmac/overlay    a UNIVERSAL prebuilt Swift overlay (no swiftc needed)
#   /usr/local/bin/lockmac            a wrapper that runs it with the prebuilt overlay
#
# Requires swiftc here (build host), but the resulting .pkg needs NOTHING but
# the system python3 on the target Mac.
#
# Signing/notarization (for Gatekeeper, needs an Apple Developer account) is
# OPTIONAL and documented in packaging/README.md. Unsigned: users right-click →
# Open, or `sudo installer -pkg lockmac-<ver>.pkg -target /`.
set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$PKG_DIR/.." && pwd)"            # the lockmac/ package root
VER="$(python3 -c "import tomllib,sys; print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo 0.1.0)"
IDENT="com.lockmac.pkg"
OUT="$ROOT/dist"
STAGE="$(mktemp -d)"
PREFIX="/usr/local/lib/lockmac"

echo "▸ building lockmac.pkg v$VER"
command -v swiftc >/dev/null || { echo "✗ swiftc required on build host"; exit 1; }
command -v pkgbuild >/dev/null || { echo "✗ pkgbuild not found (Xcode CLT)"; exit 1; }

# 1. universal Swift overlay (arm64 + x86_64) so any Mac runs it without swiftc
echo "▸ compiling universal overlay"
ARCH_DIR="$(mktemp -d)"
swiftc -target arm64-apple-macos11  "$ROOT/lockmac/overlay.swift" -o "$ARCH_DIR/overlay.arm64"
swiftc -target x86_64-apple-macos11 "$ROOT/lockmac/overlay.swift" -o "$ARCH_DIR/overlay.x86_64"
lipo -create -output "$ARCH_DIR/overlay" "$ARCH_DIR/overlay.arm64" "$ARCH_DIR/overlay.x86_64"
lipo -info "$ARCH_DIR/overlay"

# 2. assemble payload root
PAYROOT="$STAGE/root"
mkdir -p "$PAYROOT$PREFIX/lockmac" "$PAYROOT/usr/local/bin"
cp "$ROOT"/lockmac/*.py        "$PAYROOT$PREFIX/lockmac/"
cp "$ROOT"/lockmac/overlay.swift "$PAYROOT$PREFIX/lockmac/"   # kept for reference
cp "$ARCH_DIR/overlay"         "$PAYROOT$PREFIX/overlay"
chmod +x "$PAYROOT$PREFIX/overlay"

# 3. CLI wrapper: run the package with the prebuilt overlay (no swiftc on target)
cat > "$PAYROOT/usr/local/bin/lockmac" <<WRAP
#!/bin/bash
export LOCKMAC_BIN="$PREFIX/overlay"
exec /usr/bin/python3 -c "import sys; sys.path.insert(0, '$PREFIX'); from lockmac.cli import main; sys.exit(main())" "\$@"
WRAP
chmod +x "$PAYROOT/usr/local/bin/lockmac"

# 4. build the component pkg
mkdir -p "$OUT"
pkgbuild --root "$PAYROOT" --identifier "$IDENT" --version "$VER" \
         --install-location / "$OUT/lockmac-$VER.pkg"

echo "✓ built: $OUT/lockmac-$VER.pkg"
echo "  install: sudo installer -pkg \"$OUT/lockmac-$VER.pkg\" -target /"
echo "  (unsigned — for distribution, sign+notarize; see packaging/README.md)"
rm -rf "$STAGE" "$ARCH_DIR"
