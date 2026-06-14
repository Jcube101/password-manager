"""
Crypto layer for pwm.

Implements the exact contracts from SPEC.md:
- Argon2id key derivation (memory-hard, side-channel resistant)
- AES-256-GCM authenticated encryption for the vault
- Explicit on-disk header format with persisted Argon2 parameters
- Fresh salt + nonce on every encryption
- Clean, non-leaking error on decryption failure (wrong master or corruption)

NEVER roll your own primitives. We only wrap audited libraries.

See LEARNINGS.md for parameter rationale and historical decisions.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import NamedTuple

import argon2
from argon2 import low_level
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


# ---------------------------------------------------------------------
# Constants & Format (must match SPEC.md exactly)
# ---------------------------------------------------------------------

MAGIC = b"PWM1"
FORMAT_VERSION = 1

# Header layout (little-endian):
#   0:4   MAGIC
#   4:5   format_version (uint8)
#   5:9   time_cost (uint32)
#   9:13  memory_cost (uint32)
#   13:14 parallelism (uint8)
#   14:30 salt (16 bytes)
#   30:42 nonce (12 bytes)
#   42:   ciphertext (AES-GCM output = ct || 16-byte tag)

HEADER_SIZE = 42  # bytes before ciphertext
SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16  # GCM tag length (cryptography always uses 128-bit)

# Reasonable v1 defaults (see LEARNINGS.md for why these values)
# Target ~1-2.5s on a typical desktop while providing strong memory hardness.
DEFAULT_ARGON_PARAMS = {
    "time_cost": 3,
    "memory_cost": 65536,   # 64 MiB (in KiB units for Argon2)
    "parallelism": 4,
    "hash_len": 32,         # 256-bit key for AES-256-GCM
}


class VaultDecryptionError(Exception):
    """Raised for wrong master password or any corruption / tampering.

    The message is deliberately generic so we do not leak information
    that would help an attacker distinguish "bad key" from "bad data".
    """
    pass


@dataclass(frozen=True)
class ArgonParams:
    time_cost: int
    memory_cost: int
    parallelism: int

    @classmethod
    def defaults(cls) -> ArgonParams:
        return cls(
            time_cost=DEFAULT_ARGON_PARAMS["time_cost"],
            memory_cost=DEFAULT_ARGON_PARAMS["memory_cost"],
            parallelism=DEFAULT_ARGON_PARAMS["parallelism"],
        )


# ---------------------------------------------------------------------
# Low-level primitives (the contract surface)
# ---------------------------------------------------------------------

def derive_key(
    master_password: str,
    salt: bytes,
    params: ArgonParams | None = None,
) -> bytes:
    """Derive a 32-byte key from the master password using Argon2id.

    This is the ONLY place Argon2id is called in the entire project.
    """
    if params is None:
        params = ArgonParams.defaults()

    if not master_password:
        raise ValueError("Master password must not be empty")

    if len(salt) != SALT_SIZE:
        raise ValueError(f"Salt must be exactly {SALT_SIZE} bytes")

    key = low_level.hash_secret_raw(
        secret=master_password.encode("utf-8"),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost,
        parallelism=params.parallelism,
        hash_len=DEFAULT_ARGON_PARAMS["hash_len"],
        type=low_level.Type.ID,   # Argon2id (hybrid)
    )
    assert len(key) == 32, "Derived key must be 32 bytes"
    return key


def _encrypt_raw(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    """Internal: encrypt with fresh nonce. Returns (nonce, ct_with_tag)."""
    if len(key) != 32:
        raise ValueError("Key must be 32 bytes for AES-256-GCM")

    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    # We bind the header (magic + params + salt) via AAD when the caller
    # assembles the full blob. For raw encrypt we use no AAD.
    ct = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    # ct from cryptography is ciphertext || tag (16 bytes)
    return nonce, ct


def _decrypt_raw(nonce: bytes, ciphertext: bytes, key: bytes) -> bytes:
    """Internal: decrypt + authenticate. Raises VaultDecryptionError on failure."""
    if len(nonce) != NONCE_SIZE:
        raise VaultDecryptionError("Invalid nonce length")
    if len(key) != 32:
        raise VaultDecryptionError("Invalid key length")

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
        return plaintext
    except InvalidTag:
        raise VaultDecryptionError(
            "Decryption failed. Wrong master password or the vault file is corrupted."
        ) from None
    except Exception as exc:
        # Any other crypto error is also treated as "bad vault or bad key"
        raise VaultDecryptionError(
            "Decryption failed. Wrong master password or the vault file is corrupted."
        ) from exc


# ---------------------------------------------------------------------
# High-level vault (de)serialization used by the Vault layer
# ---------------------------------------------------------------------

def _pack_header(
    params: ArgonParams,
    salt: bytes,
    nonce: bytes,
) -> bytes:
    """Pack the 42-byte header exactly as defined in SPEC.md."""
    if len(salt) != SALT_SIZE or len(nonce) != NONCE_SIZE:
        raise ValueError("Bad salt or nonce length in header packing")

    header = bytearray()
    header.extend(MAGIC)
    header.append(FORMAT_VERSION)
    header.extend(struct.pack("<I", params.time_cost))
    header.extend(struct.pack("<I", params.memory_cost))
    header.append(params.parallelism)
    header.extend(salt)
    header.extend(nonce)
    assert len(header) == HEADER_SIZE
    return bytes(header)


def _unpack_header(data: bytes) -> tuple[ArgonParams, bytes, bytes]:
    """Unpack header. Returns (params, salt, nonce)."""
    if len(data) < HEADER_SIZE:
        raise VaultDecryptionError("Vault file is too small to be valid")

    if data[:4] != MAGIC:
        raise VaultDecryptionError(
            "Decryption failed. Wrong master password or the vault file is corrupted."
        )

    fmt_ver = data[4]
    if fmt_ver != FORMAT_VERSION:
        raise VaultDecryptionError(
            f"Unsupported vault format version {fmt_ver} (expected {FORMAT_VERSION}). "
            "You may need a newer version of pwm."
        )

    time_cost = struct.unpack("<I", data[5:9])[0]
    memory_cost = struct.unpack("<I", data[9:13])[0]
    parallelism = data[13]
    salt = data[14:30]
    nonce = data[30:42]

    params = ArgonParams(
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
    )
    return params, salt, nonce


def encrypt_vault(
    plaintext: bytes,
    master_password: str,
    params: ArgonParams | None = None,
) -> bytes:
    """Encrypt the vault plaintext and return the full on-disk blob.

    Always uses fresh salt and fresh nonce.
    The returned bytes are exactly what should be written to the vault file.
    """
    if params is None:
        params = ArgonParams.defaults()

    salt = os.urandom(SALT_SIZE)
    key = derive_key(master_password, salt, params)

    # For AAD we use the header prefix up to (but not including) the nonce,
    # i.e. the first 30 bytes once we know the nonce. We assemble in two steps.
    # First encrypt with no AAD for the raw content (simpler), then we will
    # include AAD = header-without-nonce when we have the full picture.
    #
    # Per SPEC v1 we bind magic+fmt+params+salt as AAD.
    # We do this by building the partial header first.
    nonce = os.urandom(NONCE_SIZE)

    # Build partial header (no nonce yet) for AAD
    partial_header = bytearray()
    partial_header.extend(MAGIC)
    partial_header.append(FORMAT_VERSION)
    partial_header.extend(struct.pack("<I", params.time_cost))
    partial_header.extend(struct.pack("<I", params.memory_cost))
    partial_header.append(params.parallelism)
    partial_header.extend(salt)
    aad = bytes(partial_header)  # 30 bytes

    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, associated_data=aad)

    # Now assemble the real header (includes nonce)
    full_header = _pack_header(params, salt, nonce)
    return full_header + ct


def decrypt_vault(
    blob: bytes,
    master_password: str,
) -> tuple[bytes, ArgonParams]:
    """Decrypt a full vault blob.

    Returns (plaintext, params_used).
    Raises VaultDecryptionError on any failure (wrong pw, corrupt, tamper, bad format).
    """
    if len(blob) < HEADER_SIZE:
        raise VaultDecryptionError("Vault file is too small to be valid")

    params, salt, nonce = _unpack_header(blob)
    ciphertext = blob[HEADER_SIZE:]

    key = derive_key(master_password, salt, params)

    # Reconstruct the same AAD used at encryption time
    partial_header = bytearray()
    partial_header.extend(MAGIC)
    partial_header.append(FORMAT_VERSION)
    partial_header.extend(struct.pack("<I", params.time_cost))
    partial_header.extend(struct.pack("<I", params.memory_cost))
    partial_header.append(params.parallelism)
    partial_header.extend(salt)
    aad = bytes(partial_header)

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=aad)
        return plaintext, params
    except InvalidTag:
        raise VaultDecryptionError(
            "Decryption failed. Wrong master password or the vault file is corrupted."
        ) from None
    except Exception as exc:
        raise VaultDecryptionError(
            "Decryption failed. Wrong master password or the vault file is corrupted."
        ) from exc


# ---------------------------------------------------------------------
# Convenience for tests / inspection (not part of the production hot path)
# ---------------------------------------------------------------------

def get_header_info(blob: bytes) -> dict:
    """Return human-readable info from the header without decrypting.

    Useful for `pwm inspect` (future) and for debugging / learning.
    Never returns any decrypted material.
    """
    if len(blob) < HEADER_SIZE:
        return {"valid": False, "reason": "too small"}

    if blob[:4] != MAGIC:
        return {"valid": False, "reason": "bad magic"}

    fmt = blob[4]
    time_cost = struct.unpack("<I", blob[5:9])[0]
    mem = struct.unpack("<I", blob[9:13])[0]
    par = blob[13]

    return {
        "valid": True,
        "magic": blob[:4].decode("ascii", errors="replace"),
        "format_version": fmt,
        "time_cost": time_cost,
        "memory_cost": mem,
        "parallelism": par,
        "salt_hex": blob[14:30].hex(),
        "nonce_hex": blob[30:42].hex(),
        "ciphertext_len": len(blob) - HEADER_SIZE,
    }
