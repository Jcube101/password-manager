"""
Signet sidecar.

Wraps the current 32-byte vault key so Windows Hello can unwrap it later.
The master password is never an argument to this module and is never written
into the file.

The on-disk layout is SPEC.md §13.2. Tests pass a fake PRF output. The
Windows Hello call is a separate step and does not belong here.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from pwm.crypto import VaultDecryptionError, decrypt_vault_with_key

MAGIC = b"SGN1"
VERSION = 1
PRF_SALT_SIZE = 32
VAULT_KEY_SIZE = 32
NONCE_SIZE = 12
# Domain separation for the non-32-byte case. A 32-byte PRF output is used
# as the AES key directly and does not go through HKDF.
HKDF_INFO = b"signet-wrap-v1"

# magic + version + cred-id length + prf salt + nonce + gcm tag, before any
# credential id bytes or the 32-byte key ciphertext.
_MIN_WITHOUT_CRED_ID = 4 + 1 + 2 + PRF_SALT_SIZE + NONCE_SIZE + 16


class SidecarError(Exception):
    """The sidecar could not be opened. Wrong PRF output, or a damaged file."""


class SidecarMismatch(SidecarError):
    """The sidecar opened, but its key does not decrypt this vault.

    Signet asks for the master password and enrolls again. This happens
    after a CLI save rotates the salt.
    """


@dataclass(frozen=True)
class ParsedSidecar:
    """Public fields of a sidecar. The vault key is not one of them."""

    credential_id: bytes
    prf_salt: bytes
    nonce: bytes
    ciphertext: bytes


def sidecar_path(vault_path: Path) -> Path:
    """Vault path plus `.signet`. `vault` becomes `vault.signet`."""
    return Path(str(vault_path) + ".signet")


def wrapping_key(prf_output: bytes) -> bytes:
    """AES-256 key for the sidecar. 32-byte PRF output is used as-is."""
    if len(prf_output) == VAULT_KEY_SIZE:
        return prf_output
    if not prf_output:
        raise ValueError("PRF output must not be empty")

    return HKDF(
        algorithm=hashes.SHA256(),
        length=VAULT_KEY_SIZE,
        salt=None,
        info=HKDF_INFO,
    ).derive(prf_output)


def build_sidecar(
    vault_key: bytes,
    prf_output: bytes,
    *,
    credential_id: bytes,
    prf_salt: bytes,
) -> bytes:
    """Encrypt the vault key. A fresh nonce is chosen on every call."""
    if len(vault_key) != VAULT_KEY_SIZE:
        raise ValueError(f"Vault key must be exactly {VAULT_KEY_SIZE} bytes")
    if len(prf_salt) != PRF_SALT_SIZE:
        raise ValueError(f"PRF salt must be exactly {PRF_SALT_SIZE} bytes")
    if not credential_id or len(credential_id) > 0xFFFF:
        raise ValueError("Credential id length must be 1..65535 bytes")

    nonce = os.urandom(NONCE_SIZE)
    aad = _prefix(credential_id, prf_salt)
    ciphertext = AESGCM(wrapping_key(prf_output)).encrypt(nonce, vault_key, aad)
    return aad + nonce + ciphertext


def parse_sidecar(blob: bytes) -> ParsedSidecar:
    """Read the public fields. Does not decrypt."""
    if len(blob) < _MIN_WITHOUT_CRED_ID + 1:
        raise SidecarError("Sidecar could not be opened.")
    if blob[:4] != MAGIC:
        raise SidecarError("Sidecar could not be opened.")

    version = blob[4]
    if version != VERSION:
        raise SidecarError(
            f"Unsupported sidecar version {version} (expected {VERSION})."
        )

    cred_len = struct.unpack("<H", blob[5:7])[0]
    if cred_len == 0:
        raise SidecarError("Sidecar could not be opened.")

    cred_end = 7 + cred_len
    salt_end = cred_end + PRF_SALT_SIZE
    nonce_end = salt_end + NONCE_SIZE
    if len(blob) < nonce_end + VAULT_KEY_SIZE + 16:
        raise SidecarError("Sidecar could not be opened.")

    return ParsedSidecar(
        credential_id=blob[7:cred_end],
        prf_salt=blob[cred_end:salt_end],
        nonce=blob[salt_end:nonce_end],
        ciphertext=blob[nonce_end:],
    )


def unwrap_vault_key(blob: bytes, prf_output: bytes) -> bytes:
    """Return the 32-byte vault key. Raises SidecarError on failure."""
    parsed = parse_sidecar(blob)
    if not prf_output:
        raise SidecarError("Sidecar could not be opened.")

    aad = _prefix(parsed.credential_id, parsed.prf_salt)
    try:
        key = wrapping_key(prf_output)
    except ValueError:
        raise SidecarError("Sidecar could not be opened.") from None

    try:
        vault_key = AESGCM(key).decrypt(parsed.nonce, parsed.ciphertext, aad)
    except InvalidTag:
        raise SidecarError("Sidecar could not be opened.") from None
    except Exception:
        raise SidecarError("Sidecar could not be opened.") from None

    if len(vault_key) != VAULT_KEY_SIZE:
        raise SidecarError("Sidecar could not be opened.")
    return vault_key


def rewrite_sidecar(blob: bytes, vault_key: bytes, prf_output: bytes) -> bytes:
    """Write the vault key again. The PRF salt and credential id stay."""
    parsed = parse_sidecar(blob)
    return build_sidecar(
        vault_key,
        prf_output,
        credential_id=parsed.credential_id,
        prf_salt=parsed.prf_salt,
    )


def open_with_sidecar(vault_blob: bytes, sidecar_blob: bytes, prf_output: bytes) -> bytes:
    """Decrypt a vault using a sidecar. A stale key fails closed."""
    vault_key = unwrap_vault_key(sidecar_blob, prf_output)
    try:
        plaintext, _params = decrypt_vault_with_key(vault_blob, vault_key)
    except VaultDecryptionError:
        raise SidecarMismatch(
            "Sidecar does not match this vault. The master password is required."
        ) from None
    return plaintext


def read_sidecar(vault_path: Path) -> bytes | None:
    """Return the sidecar bytes, or None when the file is absent."""
    path = sidecar_path(vault_path)
    if not path.is_file():
        return None
    return path.read_bytes()


def write_sidecar(vault_path: Path, blob: bytes) -> Path:
    """Atomic write of a sidecar next to the vault. Returns the path."""
    path = sidecar_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(path) + ".tmp")
    with open(tmp_path, "wb") as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    return path


def _prefix(credential_id: bytes, prf_salt: bytes) -> bytes:
    """Associated data: everything before the nonce."""
    header = bytearray()
    header.extend(MAGIC)
    header.append(VERSION)
    header.extend(struct.pack("<H", len(credential_id)))
    header.extend(credential_id)
    header.extend(prf_salt)
    return bytes(header)
