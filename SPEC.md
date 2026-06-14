# SPEC.md — pwm Password Manager Implementation Contract

This document is the **binding implementation contract** for every layer of the pwm password manager.

It is precise enough that a competent developer (or subagent) can implement any single layer in isolation, write tests against it, and have the pieces compose correctly.

**If you need to change behavior described here, update this file first** (with date and rationale in LEARNINGS.md) and get explicit agreement before coding against the new contract.

Current target: v1 (fully functional local CLI password manager).

---

## 1. High-Level Invariants (Never Violate)

- Everything is **local-only**. No network calls, no telemetry, no cloud sync in v1.
- The **master password never leaves the user's head and is never written to disk** (plaintext or otherwise).
- The on-disk artifact is **one encrypted file** (the "vault").
- All cryptography uses only well-audited libraries: `cryptography` (AES-GCM) and `argon2-cffi` (Argon2id). No custom primitives, no custom modes, no "simple XOR".
- Every encryption operation uses a **fresh cryptographically random salt (16 bytes)** and a **fresh cryptographically random nonce (12 bytes)**.
- Writes to the vault file are **atomic** (temp file + rename/replace).
- The CLI command is exactly `pwm`.
- Passwords and the master password are **never** logged, printed in stack traces, or stored in command history in a way the tool can control.
- The tool must degrade gracefully on wrong master password or corrupted vault with a single non-leaking message.

---

## 2. Data Model

### 2.1 Entry

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

@dataclass
class Entry:
    id: str                    # UUID4 string, stable, never changes
    label: str                 # Human label. Must be unique within a vault for add/get/copy by label.
    username: str | None = None
    password: str              # The secret. Always present for password entries in v1.
    url: str | None = None
    notes: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: str            # ISO-8601 UTC, e.g. "2026-06-14T12:34:56Z"
    updated_at: str            # ISO-8601 UTC, updated on any modification
```

Rules:
- `label` is the primary user-facing key. It is case-sensitive for exact lookup.
- `id` is used internally for future-proofing (label renames, etc.).
- `tags` is a list of short strings; duplicates within one entry are not meaningful.
- Timestamps are always generated with `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` (or equivalent that produces `Z` suffix).

### 2.2 Vault Content (the plaintext that gets encrypted)

```json
{
  "version": 1,
  "created_at": "2026-06-14T12:00:00Z",
  "entries": [ /* array of Entry objects as dicts */ ]
}
```

- `version` inside the JSON is the **data version** (currently 1). It is independent of the on-disk format version.
- The list may be empty.

---

## 3. On-Disk Vault Format (Exact Binary Layout)

The file is a binary blob. No base64, no extra encoding at the top level.

Byte layout (all multi-byte integers are **little-endian**):

| Offset | Length | Content | Notes |
|--------|--------|---------|-------|
| 0      | 4      | Magic   | `b"PWM1"` (ASCII) — identifies the file type and major version |
| 4      | 1      | Format version | `0x01` (uint8). Increment only on breaking header changes. |
| 5      | 4      | time_cost     | uint32 (Argon2 parameter) |
| 9      | 4      | memory_cost   | uint32 (Argon2 parameter, in KiB) |
| 13     | 1      | parallelism   | uint8 (Argon2 parameter) |
| 14     | 16     | salt          | 16 random bytes (for Argon2id) |
| 30     | 12     | nonce         | 12 random bytes (for AES-256-GCM) |
| 42     | rest   | ciphertext    | Output of `AESGCM.encrypt(nonce, plaintext, associated_data)` — this includes the 16-byte authentication tag appended by the cryptography library |

**Associated data (AAD) for AES-GCM** (for v1):
- The first 30 bytes of the file (magic through salt). This binds the header parameters to the ciphertext.

**Plaintext** (before encryption / after successful decryption):
- UTF-8 encoded JSON exactly matching the structure in section 2.2 (no extra whitespace requirements, but the implementation should produce compact or pretty consistently — compact is fine).

**Key derivation**:
- 32-byte key = `argon2.low_level.hash_secret_raw(
    secret=master.encode("utf-8"),
    salt=salt,
    time_cost=time_cost,
    memory_cost=memory_cost,
    parallelism=parallelism,
    hash_len=32,
    type=argon2.low_level.Type.ID
  )`

**Encryption / Decryption**:
- Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM(key).encrypt(nonce, plaintext, aad)` → returns `ct || tag` (16 bytes).
- Decrypt with the matching `.decrypt(...)`. Any `InvalidTag` or other failure must be turned into a clean "wrong master or corrupted" error. Do not leak `InvalidTag` details to the user.

**Creating a new vault**:
- Generate fresh salt + nonce.
- Use the chosen Argon2 parameters (hard-coded defaults in one place, overridable for tests).
- Encrypt an initial JSON with `"entries": []`.
- Write the 42+ byte header + ciphertext atomically.

**Re-encrypting** (any save, including `change-master`):
- Always generate **new** salt and **new** nonce.
- Re-derive key from the (new or same) master + new salt.
- Re-encrypt the current in-memory entries under the new parameters.

---

## 4. Crypto Layer API Contract (Minimal, Testable)

The crypto module should expose (exact names may vary slightly as long as behavior matches):

```python
from pathlib import Path
from typing import NamedTuple

class ArgonParams(NamedTuple):
    time_cost: int
    memory_cost: int
    parallelism: int

DEFAULT_ARGON_PARAMS = ArgonParams(time_cost=3, memory_cost=65536, parallelism=4)

def derive_key(
    master_password: str,
    salt: bytes,
    params: ArgonParams = DEFAULT_ARGON_PARAMS,
) -> bytes:
    """Returns exactly 32 bytes. Raises on obviously bad input."""
    ...

def encrypt_vault(
    plaintext: bytes,
    key: bytes,
    params: ArgonParams,
) -> tuple[bytes, bytes, bytes]:
    """
    Returns (salt, nonce, ciphertext_with_tag).
    The caller is responsible for writing the full on-disk format.
    Generates fresh salt and nonce internally.
    """

def decrypt_vault(
    salt: bytes,
    nonce: bytes,
    ciphertext: bytes,
    key: bytes,
) -> bytes:
    """Returns plaintext bytes or raises VaultDecryptionError (our own exception)."""
    ...

class VaultDecryptionError(Exception):
    """Generic, non-leaking exception for wrong password or corruption."""
    ...
```

Tests required for this layer (must pass before higher layers are trusted):
- Roundtrip with known master + known params → identical plaintext.
- Wrong master → `VaultDecryptionError` (not a raw `InvalidTag`).
- Tampered ciphertext or AAD → `VaultDecryptionError`.
- Multiple encryptions of the same plaintext with same key produce different salts/nonces/ciphertexts (probabilistically).
- Parameters are correctly serialized and re-used on decrypt.

---

## 5. Vault Manager / Storage Layer Contract

Responsible for:
- Knowing the vault file path (from `platformdirs` or `--vault-path`).
- Loading the header + deciding whether the file exists.
- `unlock(master: str)` → derives key, decrypts, populates in-memory list of `Entry`.
- Keeping the decrypted state in memory only while the process lives.
- All mutations happen on the in-memory list, then `save()` re-serializes + re-encrypts + atomically writes.
- `change_master(old: str, new: str)` → requires current unlock or re-unlock with old, then saves under new master.

High-level methods (names illustrative):

```python
class Vault:
    def __init__(self, vault_path: Path | None = None): ...
    def exists(self) -> bool: ...
    def unlock(self, master: str) -> None: ...
    def lock(self) -> None: ...
    def is_unlocked(self) -> bool: ...

    # CRUD
    def add(self, label: str, **kwargs) -> Entry: ...
    def get(self, label: str) -> Entry | None: ...
    def search(self, query: str) -> list[Entry]: ...
    def delete(self, label: str) -> bool: ...
    def update(self, label: str, **changes) -> Entry: ...

    def list_all(self) -> list[Entry]: ...
    def save(self) -> None: ...
    def change_master(self, new_master: str) -> None: ...  # assumes already unlocked with old
```

- `search` is simple case-insensitive substring match across label, username, url, notes, and tags (joined).
- `label` uniqueness is enforced on `add` and on rename via `update`.
- All `save()` calls must produce a valid header + fresh salt/nonce + re-encrypted content.
- The Vault object must support being used from the CLI (one instance per invocation is typical).

---

## 6. Password Generator Contract

```python
def generate_password(
    length: int = 20,
    use_upper: bool = True,
    use_lower: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    symbols: str = "!@#$%^&*()_+-=[]{}|;:,.<>?",
    exclude: str = "0O1lI|`'\"\\",
) -> str:
    """Returns a cryptographically secure password using only `secrets`."""
```

Rules:
- At least one character class must be enabled, otherwise raise `ValueError`.
- After filtering the allowed alphabet by `exclude`, the final alphabet must have >= 10 characters or the call raises.
- Uses `secrets.choice` in a loop (or `secrets.token_bytes` + rejection sampling for perfect uniformity if desired — simple loop is acceptable for v1).
- Must be deterministic only via its parameters (no global state).

CLI exposure:
- `pwm generate [OPTIONS]` prints the password to stdout.
- `--copy` also copies it to clipboard (same mechanism as `copy` command).
- Flags: `--length`, `--no-upper`, `--no-lower`, `--no-digits`, `--no-symbols`, `--symbols "..."`, `--exclude "..."`.

---

## 7. CLI Contract (typer + rich)

All commands live under a single `typer.Typer` app.

Global options (available on most commands):
- `--vault-path PATH` : override the default user-data vault location (useful for testing).
- `--help` : standard.

### 7.1 `pwm init`
- If vault already exists: error "Vault already initialized."
- Prompts twice for master password (hidden).
- Creates empty vault with the master.
- Prints success + location of the vault file (for backup awareness).

Alternative: implicit init on first `pwm add` is also acceptable if clearly documented.

### 7.2 `pwm generate`
(See generator contract above.)

### 7.3 `pwm add`
Required:
- `--label TEXT` (or positional `label`)

Optional:
- `--username TEXT`
- `--password TEXT` (if omitted and not `--generate`, prompt once hidden)
- `--generate` : generate a strong password (respecting any generator flags)
- `--url TEXT`
- `--notes TEXT`
- `--tag TAG` (repeatable)

Behavior:
- If label exists → error.
- On success: save, print the created entry (password hidden unless `--show-password`).

### 7.4 `pwm list`
- Prints a Rich table: label, username, url, tags (comma), updated.
- Password column is **never** shown by default.
- `--show` or `--show-password` : shows the password column (big warning in help text).
- `--tag TAG` : filter to entries containing that tag.
- Sorted by label.

### 7.5 `pwm search <query>`
- Same table output as list.
- Case-insensitive substring search.
- If no results: friendly message.

### 7.6 `pwm get <label>`
- Shows full details for the exact label (one entry).
- Password hidden by default; `--show-password` reveals it.
- If not found: clear "No entry with label 'X'."

### 7.7 `pwm copy <label>`
- Copies the password of the exact-matching label to clipboard (via pyperclip).
- Prints "Password for 'Gmail' copied to clipboard." (no actual password printed).
- Optional `--clear-after SECONDS` (stretch for v1).
- If not found: error.

### 7.8 `pwm edit <label>`
- Allows changing any field (label rename is special — must not collide).
- Can use same flags as `add`.
- Interactive prompts for fields not supplied are acceptable.

### 7.9 `pwm delete <label>`
- Requires confirmation ("Type the label again to confirm" or simple y/n with the label shown).
- Removes the entry and saves.

### 7.10 `pwm change-master`
- Prompts for current master (or re-uses if process already unlocked).
- Prompts twice for new master.
- Re-encrypts the entire vault under the new master + fresh salt/nonce.
- On any failure during the process the old vault must remain intact (atomic write helps here).

### 7.11 General CLI Rules
- Every command that needs decrypted data prompts for the master password using `getpass.getpass("Master password: ")` unless the vault is already unlocked in this process (rare in CLI).
- Use Rich `Console` for all output.
- Use a Rich `Progress` / spinner while deriving the key (Argon2 is deliberately slow).
- Help text for any command that can show passwords must contain a security warning.
- Exit codes: 0 on success, non-zero on any error. No secret information in stdout on error paths.

---

## 8. File & Path Contract

- Default vault location: `platformdirs.user_data_dir("pwm") / "vault"`
  - Windows example: `C:\Users\<user>\AppData\Roaming\pwm\vault`
- The directory is created on first write if it does not exist.
- The vault file itself has no extension.
- `--vault-path` overrides everything (the parent dir is used as-is; the filename is still "vault" unless an explicit file is given).
- During tests we must be able to pass a temp path and never touch the real user dir.

---

## 9. Security & Operational Requirements

- Derived key objects are deleted and garbage collected after use where practical (`del key; gc.collect()`).
- No plaintext of entries or master ever written to disk except inside the correctly formatted encrypted vault.
- Clipboard usage is documented with its limitations (see LEARNINGS.md).
- On first use or `init`, the tool should print a short "backup your vault file" reminder.
- The tool must continue to function if the user moves the vault file (via `--vault-path`).

---

## 10. Dependencies (Runtime — v1)

- typer >= 0.9
- rich >= 13
- cryptography >= 42
- argon2-cffi >= 23
- pyperclip >= 1.8
- platformdirs >= 4

Dev / test (optional for core functionality but required for the project):
- pytest
- ruff (or black + isort)

The `pyproject.toml` must declare an entry point:
```toml
[project.scripts]
pwm = "pwm.cli:app"
```

---

## 11. Testing Requirements (Minimum)

- `tests/test_crypto.py`:
  - Roundtrips
  - Wrong-key failure path
  - Tamper detection
  - Parameter roundtrip through header serialization
- `tests/test_vault.py`:
  - Create, unlock, add, list, search, delete, save, re-unlock
  - change_master
  - Atomic write behavior (can be tested by inspecting temp files or using temp dirs)
- CLI tests (recommended): use `typer.testing.CliRunner` for the happy paths that do not require interactive password entry, or monkeypatch `getpass`.

All crypto tests must be runnable without a real TTY.

---

## 12. Documentation & Comments

- Every public function and the crypto module header must have clear comments explaining the security model.
- The on-disk format and Argon2 parameter meaning must be commented where the constants are defined.
- User-facing help text and error messages are part of the contract.

---

This SPEC is the single source of truth for v1 implementation. When the build is complete, the final state of the code + tests must be consistent with (or an explicitly documented extension of) this document.

Initial version: 2026-06-14
