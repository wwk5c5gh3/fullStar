class Lockmac < Formula
  include Language::Python::Virtualenv

  desc "macOS privacy veil — black out the screen (not a lock) with Telegram remote"
  homepage "https://github.com/wwk5c5gh3/fullStar"
  # Stable: a published release tarball of the lockmac/ subtree. Fill sha256 with:
  #   git archive --format=tar.gz --prefix=lockmac-0.1.0/ HEAD:lockmac > lockmac-0.1.0.tar.gz
  #   shasum -a 256 lockmac-0.1.0.tar.gz
  url "https://github.com/wwk5c5gh3/fullStar/releases/download/lockmac-v0.1.0/lockmac-0.1.0.tar.gz"
  # sha256 of `git archive --format=tar.gz --prefix=lockmac-0.1.0/ HEAD:lockmac`
  # at the tagged commit; regenerate if the subtree changes before tagging.
  sha256 "42ea7fc553bbba036462df867cbb4422d662260639d71a5a64598c8fbb3ad8f4"
  license "MIT"
  version "0.1.0"

  # Install with no release needed:  brew install --HEAD <this-formula>
  head "https://github.com/wwk5c5gh3/fullStar.git", branch: "main"

  depends_on "python@3.12"
  # The Swift overlay is compiled on first run; that needs Xcode Command Line
  # Tools (swiftc). Homebrew can't depend on those, so document it in the caveats.

  def install
    # release tarball is the lockmac/ subtree root; HEAD clones the whole repo
    src = build.head? ? buildpath/"lockmac" : buildpath
    venv = virtualenv_create(libexec, "python3.12")
    venv.pip_install src
    bin.install_symlink libexec/"bin/lockmac"
    bin.install_symlink libexec/"bin/veilkit"
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
