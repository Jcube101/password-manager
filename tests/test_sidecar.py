"""
Sidecar tests. The PRF output is fake. Nothing here calls Windows Hello.

SPEC.md §13.5 requires four results: a missing sidecar still opens with the
master, a matching sidecar round-trips the vault key, a CLI salt rotation
fails closed until the master is typed, and a Signet save keeps the salt
and uses a fresh nonce.
"""

import os

import pytest

from pwm.crypto import (
    ArgonParams,
    VaultDecryptionError,
    decrypt_vault,
    decrypt_vault_with_key,
    derive_key,
    encrypt_vault,
    get_header_info,
    reencrypt_vault_with_key,
)
from pwm.sidecar import (
    HKDF_INFO,
    SidecarError,
    SidecarMismatch,
    build_sidecar,
    open_with_sidecar,
    parse_sidecar,
    read_sidecar,
    rewrite_sidecar,
    sidecar_path,
    unwrap_vault_key,
    wrapping_key,
    write_sidecar,
)

TINY = ArgonParams(time_cost=1, memory_cost=8, parallelism=1)
MASTER = "test master password"
PLAINTEXT = b'{"version":1,"entries":[]}'


def _salt_of(blob: bytes) -> bytes:
    return bytes.fromhex(get_header_info(blob)["salt_hex"])


def _nonce_of(blob: bytes) -> str:
    return get_header_info(blob)["nonce_hex"]


def _vault_key(blob: bytes) -> bytes:
    return derive_key(MASTER, _salt_of(blob), TINY)


def test_missing_sidecar_still_opens_with_master(tmp_path):
    blob = encrypt_vault(PLAINTEXT, MASTER, TINY)
    vault_path = tmp_path / "vault"
    vault_path.write_bytes(blob)

    assert sidecar_path(vault_path) == tmp_path / "vault.signet"
    assert read_sidecar(vault_path) is None

    recovered, _params = decrypt_vault(blob, MASTER)
    assert recovered == PLAINTEXT


def test_matching_sidecar_roundtrips_vault_key():
    blob = encrypt_vault(PLAINTEXT, MASTER, TINY)
    key = _vault_key(blob)
    prf = os.urandom(32)
    sidecar = build_sidecar(
        key,
        prf,
        credential_id=b"cred-id",
        prf_salt=os.urandom(32),
    )

    assert unwrap_vault_key(sidecar, prf) == key
    assert open_with_sidecar(blob, sidecar, prf) == PLAINTEXT
    recovered, _params = decrypt_vault_with_key(blob, unwrap_vault_key(sidecar, prf))
    assert recovered == PLAINTEXT


def test_cli_salt_rotation_fails_closed_until_master_is_typed():
    blob = encrypt_vault(PLAINTEXT, MASTER, TINY)
    key = _vault_key(blob)
    prf = os.urandom(32)
    credential_id = os.urandom(32)
    prf_salt = os.urandom(32)
    sidecar = build_sidecar(
        key,
        prf,
        credential_id=credential_id,
        prf_salt=prf_salt,
    )

    rotated = encrypt_vault(PLAINTEXT, MASTER, TINY)
    assert _salt_of(rotated) != _salt_of(blob)

    with pytest.raises(SidecarMismatch):
        open_with_sidecar(rotated, sidecar, prf)

    # The master still opens the rotated vault. Re-enroll wraps the new key.
    assert decrypt_vault(rotated, MASTER)[0] == PLAINTEXT
    new_key = _vault_key(rotated)
    enrolled = build_sidecar(
        new_key,
        prf,
        credential_id=credential_id,
        prf_salt=prf_salt,
    )
    assert open_with_sidecar(rotated, enrolled, prf) == PLAINTEXT
    assert parse_sidecar(enrolled).prf_salt == prf_salt
    assert parse_sidecar(enrolled).credential_id == credential_id


def test_signet_save_keeps_salt_and_uses_a_fresh_nonce():
    blob = encrypt_vault(PLAINTEXT, MASTER, TINY)
    key = _vault_key(blob)
    prf = os.urandom(32)
    sidecar = build_sidecar(
        key,
        prf,
        credential_id=b"cred",
        prf_salt=os.urandom(32),
    )

    updated = b'{"version":1,"entries":[{"label":"mail"}]}'
    saved = reencrypt_vault_with_key(updated, blob, key)
    rewritten = rewrite_sidecar(sidecar, key, prf)

    assert _salt_of(saved) == _salt_of(blob)
    assert _nonce_of(saved) != _nonce_of(blob)
    assert parse_sidecar(rewritten).prf_salt == parse_sidecar(sidecar).prf_salt
    assert parse_sidecar(rewritten).nonce != parse_sidecar(sidecar).nonce
    assert unwrap_vault_key(rewritten, prf) == key
    assert open_with_sidecar(saved, rewritten, prf) == updated
    assert decrypt_vault(saved, MASTER)[0] == updated

    with pytest.raises(VaultDecryptionError):
        decrypt_vault(saved, "wrong master")


def test_thirty_two_byte_prf_is_the_key_and_other_lengths_use_hkdf():
    direct = os.urandom(32)
    assert wrapping_key(direct) == direct

    short = os.urandom(16)
    derived = wrapping_key(short)
    assert len(derived) == 32
    assert derived != short
    assert wrapping_key(short) == derived
    assert derived != wrapping_key(os.urandom(16))
    assert HKDF_INFO == b"signet-wrap-v1"

    key = os.urandom(32)
    prf_salt = os.urandom(32)
    sidecar = build_sidecar(key, short, credential_id=b"id", prf_salt=prf_salt)
    assert unwrap_vault_key(sidecar, short) == key
    with pytest.raises(SidecarError):
        unwrap_vault_key(sidecar, direct)


def test_tampered_sidecar_and_wrong_prf_fail_closed():
    key = os.urandom(32)
    prf = os.urandom(32)
    sidecar = bytearray(
        build_sidecar(key, prf, credential_id=b"abc", prf_salt=os.urandom(32))
    )
    sidecar[-1] ^= 0x01
    with pytest.raises(SidecarError) as tamper:
        unwrap_vault_key(bytes(sidecar), prf)
    assert "could not be opened" in str(tamper.value)

    intact = build_sidecar(key, prf, credential_id=b"abc", prf_salt=os.urandom(32))
    with pytest.raises(SidecarError):
        unwrap_vault_key(intact, os.urandom(32))


def test_write_sidecar_is_atomic_and_replaces_the_temp_file(tmp_path):
    vault_path = tmp_path / "vault"
    blob = build_sidecar(
        os.urandom(32),
        os.urandom(32),
        credential_id=b"cred",
        prf_salt=os.urandom(32),
    )
    written = write_sidecar(vault_path, blob)

    assert written == tmp_path / "vault.signet"
    assert read_sidecar(vault_path) == blob
    assert not (tmp_path / "vault.signet.tmp").exists()


def test_cli_encrypt_still_rotates_the_salt():
    first = encrypt_vault(PLAINTEXT, MASTER, TINY)
    second = encrypt_vault(PLAINTEXT, MASTER, TINY)
    assert _salt_of(first) != _salt_of(second)
    assert _nonce_of(first) != _nonce_of(second)
