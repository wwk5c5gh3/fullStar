# Distributing lockmac

Three ways to ship it, easiest → most polished.

## B. One-line installer (`install.sh`)

Lowest effort. Users run:

```bash
# from a clone:
./lockmac/install.sh
# or remote:
curl -fsSL https://raw.githubusercontent.com/wwk5c5gh3/fullStar/main/lockmac/install.sh | bash
```

Checks macOS + python3≥3.9 + swiftc, then `pip install` + precompiles the
overlay. Needs Xcode Command Line Tools (for swiftc).

## A. Homebrew tap (`brew install`)

Most native + auto-updates. One-time publish:

1. Make a release tarball of the `lockmac/` subtree and note its hash:
   ```bash
   git archive --format=tar.gz --prefix=lockmac-0.1.0/ HEAD:lockmac > lockmac-0.1.0.tar.gz
   shasum -a 256 lockmac-0.1.0.tar.gz
   ```
2. Upload it to a GitHub Release (tag `lockmac-v0.1.0`).
3. Create a tap repo named **`homebrew-lockmac`**, copy `Formula/lockmac.rb`
   into it, and fill in the real `url` + `sha256`.

Users then:
```bash
brew tap wwk5c5gh3/lockmac
brew install lockmac
```
(Swift overlay still compiles on first run → needs Xcode CLT; noted in caveats.)

## E. Double-clickable `.pkg`

Most turnkey for non-technical users — **no swiftc needed on the target** (the
overlay is prebuilt universal arm64+x86_64 into the package).

Build it:
```bash
./lockmac/packaging/build-pkg.sh         # → lockmac/dist/lockmac-0.1.0.pkg
```

Install (unsigned):
```bash
sudo installer -pkg lockmac/dist/lockmac-0.1.0.pkg -target /
# or double-click → right-click Open (Gatekeeper) if unsigned
```

### Sign + notarize (optional, for Gatekeeper-clean distribution)

Needs an Apple Developer account ($99/yr):

```bash
# sign
productsign --sign "Developer ID Installer: Your Name (TEAMID)" \
  dist/lockmac-0.1.0.pkg dist/lockmac-0.1.0-signed.pkg
# notarize
xcrun notarytool submit dist/lockmac-0.1.0-signed.pkg \
  --apple-id you@example.com --team-id TEAMID --password APP_SPECIFIC_PW --wait
xcrun stapler staple dist/lockmac-0.1.0-signed.pkg
```

Without signing, the .pkg still installs — users just right-click → Open the
first time, or use the `installer` CLI above.
