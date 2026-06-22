"""mac-veil — a macOS privacy veil (black-out overlay, not a lock).

Public API lives in mac_veil.core; the CLI entry point is mac_veil.cli:main.
"""
from mac_veil import core

__all__ = ["core"]
__version__ = "0.1.0"
