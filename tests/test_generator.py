"""
Basic tests for the password generator (SPEC contract).
"""

import pytest

from pwm.generator import generate_password, DEFAULT_SYMBOLS, DEFAULT_EXCLUDE


def test_default_generates_strong_password():
    pw = generate_password(length=24)
    assert len(pw) == 24
    # Should contain variety from all default classes (statistically almost certain)
    assert any(c.isupper() for c in pw)
    assert any(c.islower() for c in pw)
    assert any(c.isdigit() for c in pw)
    assert any(c in DEFAULT_SYMBOLS for c in pw)
    # No excluded chars
    assert not any(c in DEFAULT_EXCLUDE for c in pw)


def test_custom_length_and_no_symbols():
    pw = generate_password(length=12, use_symbols=False)
    assert len(pw) == 12
    assert not any(c in DEFAULT_SYMBOLS for c in pw)


def test_exclude_ambiguous():
    pw = generate_password(length=30, exclude="0O1lI")
    assert not any(c in "0O1lI" for c in pw)


def test_custom_symbols():
    syms = "#$%"
    pw = generate_password(length=10, symbols=syms, use_symbols=True)
    assert all(c in (syms + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") or c.isalnum() for c in pw)  # loose


def test_at_least_one_class_required():
    with pytest.raises(ValueError):
        generate_password(length=10, use_upper=False, use_lower=False, use_digits=False, use_symbols=False)


def test_too_small_alphabet_after_exclude():
    import string as _string
    with pytest.raises(ValueError):
        generate_password(length=10, exclude=_string.ascii_letters + _string.digits + DEFAULT_SYMBOLS)
