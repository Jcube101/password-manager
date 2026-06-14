"""
Clipboard support for pwm.

Thin wrapper around pyperclip with documentation of the security limitations.
"""

import pyperclip


def copy_to_clipboard(text: str) -> None:
    """Copy text to the system clipboard.

    WARNING: The clipboard is inherently insecure on almost all desktop platforms.
    - Other processes (including malware) can read the clipboard at any time.
    - On Windows 10+, clipboard history (Win + V) may retain the value.
    - On many systems there is no automatic timeout.

    For high-security use, type the password manually or use a password manager
    with a more isolated paste mechanism.
    """
    pyperclip.copy(text)


def clear_clipboard() -> None:
    """Best-effort attempt to clear the clipboard.

    This is racy and not guaranteed. Many clipboard managers will have
    already recorded the previous value.
    """
    try:
        pyperclip.copy("")
    except Exception:
        pass
