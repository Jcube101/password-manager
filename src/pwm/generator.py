"""
Password generator for pwm.

Uses only the `secrets` module for cryptographic randomness (never `random`).
Follows the contract in SPEC.md.

Customizable via length and character class controls.
"""

from __future__ import annotations

import secrets
import string


DEFAULT_SYMBOLS = "!@#$%^&*()_+-=[]{}|;:,.<>?"
DEFAULT_EXCLUDE = "0O1lI|`'\"\\"


def generate_password(
    length: int = 20,
    *,
    use_upper: bool = True,
    use_lower: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    symbols: str = DEFAULT_SYMBOLS,
    exclude: str = DEFAULT_EXCLUDE,
) -> str:
    """Generate a cryptographically secure password.

    At least one character class must be enabled.
    After applying `exclude`, the resulting alphabet must contain at least 10 characters.

    Args:
        length: Desired password length (must be >= 4 for reasonable security).
        use_upper: Include A-Z.
        use_lower: Include a-z.
        use_digits: Include 0-9.
        use_symbols: Include symbols from the `symbols` string.
        symbols: Custom set of symbol characters to draw from when use_symbols=True.
        exclude: Characters that must never appear in the output (helps with ambiguous fonts).

    Returns:
        A random password string.

    Raises:
        ValueError: If no character classes are enabled or final alphabet is too small.
    """
    if length < 4:
        raise ValueError("Password length must be at least 4")

    alphabet_parts: list[str] = []

    if use_upper:
        alphabet_parts.append(string.ascii_uppercase)
    if use_lower:
        alphabet_parts.append(string.ascii_lowercase)
    if use_digits:
        alphabet_parts.append(string.digits)
    if use_symbols:
        if not symbols:
            raise ValueError("Symbols requested but the symbols string is empty")
        alphabet_parts.append(symbols)

    if not alphabet_parts:
        raise ValueError("At least one character class must be enabled")

    alphabet = "".join(alphabet_parts)

    # Remove excluded characters (order preserving is not required)
    if exclude:
        alphabet = "".join(ch for ch in alphabet if ch not in exclude)

    if len(alphabet) < 10:
        raise ValueError(
            f"After exclusions the alphabet is too small ({len(alphabet)} chars). "
            "Relax the exclude list or enable more character classes."
        )

    # Use secrets for every character
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return password
