"""
Tests for the crypto layer.

These must all pass before any higher layer (vault, CLI) is trusted.
They directly validate the contract in SPEC.md.
"""

import os
import pytest

from pwm.crypto import (
    derive_key,
    encrypt_vault,
    decrypt_vault,
    VaultDecryptionError,
    ArgonParams,
    get_header_info,
    HEADER_SIZE,
    DEFAULT_ARGON_PARAMS,
)


def test_derive_key_basic():
    master = "correct horse battery staple"
    salt = os.urandom(16)
    key = derive_key(master, salt)
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_derive_key_deterministic_for_same_inputs():
    master = "super secret master"
    salt = b"\x00" * 16
    params = ArgonParams(time_cost=1, memory_cost=8, parallelism=1)  # tiny for speed in tests

    k1 = derive_key(master, salt, params)
    k2 = derive_key(master, salt, params)
    assert k1 == k2


def test_derive_key_different_for_different_salt():
    master = "same password"
    salt1 = os.urandom(16)
    salt2 = os.urandom(16)
    params = ArgonParams(time_cost=1, memory_cost=8, parallelism=1)

    k1 = derive_key(master, salt1, params)
    k2 = derive_key(master, salt2, params)
    assert k1 != k2


def test_encrypt_decrypt_roundtrip():
    master = "my master password for the test"
    plaintext = b'{"version": 1, "created_at": "2026-06-14T00:00:00Z", "entries": []}'

    blob = encrypt_vault(plaintext, master)
    recovered, params = decrypt_vault(blob, master)

    assert recovered == plaintext
    assert params.time_cost == DEFAULT_ARGON_PARAMS["time_cost"]
    assert params.memory_cost == DEFAULT_ARGON_PARAMS["memory_cost"]


def test_decrypt_wrong_master_raises_generic_error():
    master = "correct"
    wrong = "incorrect"
    blob = encrypt_vault(b"some data", master)

    with pytest.raises(VaultDecryptionError) as exc:
        decrypt_vault(blob, wrong)

    # The message must be the generic non-leaking one
    assert "Wrong master password or the vault file is corrupted" in str(exc.value)


def test_decrypt_tampered_ciphertext_raises_generic_error():
    master = "tamper test"
    blob = bytearray(encrypt_vault(b"original", master))

    # Flip a bit in the ciphertext portion (after header)
    blob[HEADER_SIZE + 5] ^= 0xFF

    with pytest.raises(VaultDecryptionError):
        decrypt_vault(bytes(blob), master)


def test_decrypt_truncated_raises():
    master = "short"
    blob = encrypt_vault(b"data", master)

    with pytest.raises(VaultDecryptionError):
        decrypt_vault(blob[:HEADER_SIZE + 5], master)


def test_header_info_does_not_leak_plaintext():
    master = "inspect"
    blob = encrypt_vault(b"this is secret", master)

    info = get_header_info(blob)
    assert info["valid"] is True
    assert info["magic"] == "PWM1"
    assert "secret" not in str(info)
    assert len(info["salt_hex"]) == 32  # 16 bytes hex
    assert len(info["nonce_hex"]) == 24  # 12 bytes hex


def test_multiple_encryptions_use_different_salts_and_nonces():
    master = "same master"
    pt = b"same plaintext"

    b1 = encrypt_vault(pt, master)
    b2 = encrypt_vault(pt, master)

    info1 = get_header_info(b1)
    info2 = get_header_info(b2)

    assert info1["salt_hex"] != info2["salt_hex"]
    assert info1["nonce_hex"] != info2["nonce_hex"]
    # Ciphertexts will also differ (probabilistically guaranteed by fresh nonce + GCM)
    assert b1 != b2


def test_roundtrip_with_custom_params():
    master = "custom params"
    pt = b'{"version":1,"entries":[{"label":"test"}]}'
    params = ArgonParams(time_cost=2, memory_cost=16384, parallelism=2)  # still fast for test

    blob = encrypt_vault(pt, master, params)
    recovered, used_params = decrypt_vault(blob, master)

    assert recovered == pt
    assert used_params.time_cost == 2
    assert used_params.memory_cost == 16384
    assert used_params.parallelism == 2
