class Lockmac < Formula
  include Language::Python::Virtualenv

  desc "macOS privacy veil — black out the screen (not a lock) with Telegram remote"
  homepage "https://github.com/wwk5c5gh3/fullStar"
  # Point at a published release tarball of the lockmac/ subtree, then fill sha256:
  #   git archive --format=tar.gz --prefix=lockmac-0.1.0/ HEAD:lockmac > lockmac-0.1.0.tar.gz
  #   shasum -a 256 lockmac-0.1.0.tar.gz
  url "https://github.com/wwk5c5gh3/fullStar/releases/download/lockmac-v0.1.0/lockmac-0.1.0.tar.gz"
  sha256 "REPLACE_WITH_TARBALL_SHA256"
  license "MIT"
  version "0.1.0"

  depends_on "python@3.12"
  # The Swift overlay is compiled on first run; that needs Xcode Command Line
  # Tools (swiftc). Homebrew can't depend on those, so document it in the caveats.

  def install
    # lockmac has no third-party Python deps, so a plain virtualenv install works.
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      lockmac compiles its Swift overlay on first use — this needs Xcode
      Command Line Tools:
        xcode-select --install

      Get started:
        lockmac setup        # password + login autostart
        lockmac tg-setup     # bind a Telegram bot for remote /lock /unlock
        lockmac on / off
    EOS
  end

  test do
    assert_match "lockMac:", shell_output("#{bin}/lockmac status")
  end
end
