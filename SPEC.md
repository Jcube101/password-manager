# SPEC.md — pwm Password Manager Implementation Contract

This document is the **binding implementation contract** for every layer of the pwm password manager.

It is precise enough that a competent developer (or subagent) can implement any single layer in isolation, write tests against it, and have the pieces compose correctly.

**If you need to change behavior described here, update this file first** (with date and rationale in LEARNINGS.md) and get explicit agreement before coding against the new contract.

Current target: v1 CLI, plus the Signet desktop window in §13. The CLI contract in §§1–12 stays in force. §13 adds a second surface. It does not change the `pwm` command or the PWM1 vault layout.

---

## 1. High-Level Invariants (Never Violate)

- Everything is **local-only**. No network calls, no telemetry, no cloud sync in v1.
- The **master password never leaves the user's head and is never written to disk** (plaintext or otherwise).
- The vault ciphertext is **one encrypted file** in the PWM1 layout below. Signet may also write a sidecar next to it (§13). The sidecar is not required to open the vault with the master password. It must not contain the master password or entry plaintext.
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

**Re-encrypting** (any CLI save, including `change-master`):
- Always generate **new** salt and **new** nonce.
- Re-derive key from the (new or same) master + new salt.
- Re-encrypt the current in-memory entries under the new parameters.

**Signet saves are the exception.** A save made by Signet while it holds only the unwrapped vault key (§13) uses a **fresh nonce** and the **existing salt**. The key does not change, so the master password is not required. CLI saves still rotate the salt. A CLI save invalidates a previously wrapped key until the user types the master in Signet once.

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

### 7.0 `pwm` (no subcommand) — landing page
- Invoking `pwm` with no subcommand prints a short Rich landing page and exits 0.
- Must **not** prompt for the master password.
- Must **not** decrypt the vault, list labels, or show an entry count.
- If no vault exists at the configured path: a first-run message that points at `pwm init` and prints that path.
- If a vault exists: path, format version, Argon2 parameters, a backup reminder, and the four daily commands (`copy`, `add --generate`, `list`, `search`).
- This is header-only (same `inspect_header()` surface as `info`). Salt, nonce, and ciphertext length stay on `pwm info`.
- `pwm --help` remains the full command list. `--vault-path` applies.

### 7.1 `pwm init`
- If vault already exists: error "Vault already initialized."
- Prompts twice for master password (hidden).
- Creates empty vault with the master.
- Prints success + location of the vault file (for backup awareness) and a reminder that the master is never stored.

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

### 7.11 `pwm backup`
- Copies the **encrypted** vault file. Must **not** prompt for the master, decrypt, or write plaintext.
- Destination directory resolution, first match wins:
  1. `--dest` / `-d`
  2. Environment variable `PWM_BACKUP_DIR`
  3. `~/pwm-backups` (created if missing)
- Output file name: `pwm-vault-YYYY-MM-DD-HHMMSS` (local time). If that name exists, append `-1`, `-2`, …
- Write via a sibling `.tmp` then `os.replace` (same atomicity rule as the live vault).
- If no vault exists: same "No vault found" error as other commands.
- On success: print the destination path and remind the user the copy still needs the master.
- Optional GPG signing is **out of scope** (roadmap stretch, not this contract).

### 7.12 General CLI Rules
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
- Signet's sidecar, when present, is the vault path plus `.signet` (a vault at `...\pwm\vault` uses `...\pwm\vault.signet`). See §13.
- `--vault-path` overrides everything (the parent dir is used as-is; the filename is still "vault" unless an explicit file is given).
- During tests we must be able to pass a temp path and never touch the real user dir.

---

## 9. Security & Operational Requirements

- Derived key objects are deleted and garbage collected after use where practical (`del key; gc.collect()`).
- No plaintext of entries or master ever written to disk except inside the correctly formatted encrypted vault. The Signet sidecar (§13) may hold the current vault key only inside AES-GCM, wrapped by a Windows Hello PRF output. It must not hold the master password, a PIN, or entry plaintext.
- Clipboard usage is documented with its limitations (see LEARNINGS.md).
- On first use or `init`, the tool should print a short "backup your vault file" reminder **and** that the master password is unrecoverable (write it on paper; a file copy is not enough).
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

---

## 13. Signet (desktop window)

Signet is a local desktop window on this PC. It reads and writes the same vault file as `pwm`. The command name stays `pwm`. Typing `pwm` does not open Signet. Signet is not a hosted website, not a browser extension, and not a terminal UI.

You start Signet by clicking it. The install puts a Start menu entry and a desktop shortcut, both named Signet. Today that program does not exist yet. Until it is built, the only way in is the `pwm` command in a terminal.

No code is required by this section until implementation starts. The behavior below is the contract.

### 13.1 Unlock

Daily unlock is the Windows Hello PIN **already used to sign in to this Windows account**. Signet does not create, store, or rotate a PIN. It does not offer a shorter PIN of its own. A 4-digit app PIN is out of scope and must not be added as a substitute for Hello.

Windows Hello may accept a fingerprint or face instead of the PIN when those are enrolled on the laptop. That is the same Hello prompt, not a second credential.

First trust, once:

1. The user types the master password.
2. Signet unlocks the vault with the existing Argon2id + AES-GCM path.
3. Signet asks Windows to create a passkey on the platform authenticator (Windows Hello only), with user verification required and the PRF / hmac-secret extension enabled.
4. A fresh 32-byte PRF salt is generated and stored in the sidecar. The PRF output wraps the **current 32-byte vault key**, not the master password.
5. The master password is discarded from memory. It is never written to the sidecar.

After that, opening Signet is the Hello prompt. Hello returns the PRF output. Signet unwraps the vault key and decrypts the vault. A cancelled or failed Hello prompt shows no entries.

Signet never learns the PIN digits, so a Windows PIN change is not something the user configures inside Signet. Windows updates its own PIN. The passkey stays. The next Hello prompt asks for the new laptop PIN, and Signet receives the same unwrap secret as before. The user does nothing in Signet. Removing the PIN, or clearing the TPM, can destroy the passkey. Signet then asks for the master password, once, to enroll again.

The master password remains the other way in: a new computer, a Windows reinstall, Hello failure, a missing sidecar, or a vault whose key no longer matches the sidecar (including after `pwm change-master` or any other CLI save that rotated the salt). The CLI keeps prompting for the master with `getpass`. A Drive copy of the vault still opens with the master that was current when that copy was made. The PRF secret does not travel with the file.

### 13.2 Sidecar

Path: the vault path plus `.signet`.

The sidecar is local. It is gitignored with the vault. Copying it to another computer does not unlock the vault there.

Byte layout, little-endian:

| Offset | Length | Content |
|--------|--------|---------|
| 0 | 4 | Magic `b"SGN1"` |
| 4 | 1 | Version `0x01` |
| 5 | 2 | Credential id length (uint16) |
| 7 | N | Credential id |
| 7+N | 32 | PRF salt |
| 39+N | 12 | AES-GCM nonce, fresh every time the sidecar is written |
| 51+N | rest | Ciphertext of the 32-byte vault key, including the 16-byte GCM tag |

Associated data is everything before the nonce (magic through PRF salt).

The wrapping key is the PRF output. When that output is 32 bytes, use it directly as an AES-GCM key from `cryptography`. When it is not, derive 32 bytes with HKDF-SHA256 from `cryptography` and use that. Do not invent another cipher. Do not replace Argon2id for the master password.

Writes are atomic (sibling `.tmp`, then replace), same rule as the vault.

On every Signet save, rewrite the sidecar with the current vault key and a fresh nonce. The PRF salt stays the one from enrollment unless the user enrolls again.

### 13.3 Lock

A successful Hello unlock lasts 24 hours. The clock starts at that unlock and is not reset by later clicks. Sleep, lid close, and the Windows lock do not end it. Windows may still ask for the laptop PIN to show the desktop. Signet does not ask a second time during those 24 hours.

The vault key stays in memory for that period. Anyone who can use the unlocked Windows session can use Signet. Quitting Signet ends the session early. When 24 hours have passed, or the user starts Signet again after quitting, the next unlock is the Hello prompt again, not the master password, as long as the sidecar still matches.

A secret revealed with View is covered on sleep, on the Windows lock, on leaving the entry, and on pressing View again. Coming back within 24 hours shows the list without Hello. View asks for Hello again before showing that secret.

### 13.4 Window

The title is **Signet**. The palette is Ink: near-black surfaces (`#141414` window, `#1c1c1c` panels), warm off-white text (`#f3f1ea`), muted text `#9a958a`, borders `#2e2e2e`, one brass accent `#d6a25e`.

After unlock the list is the working surface and takes most of the window. Each row shows the label, the username, and every tag. Secrets stay off the list. The user can filter by label, username, and tag, and sort the list. Choosing one tag shows every entry that includes it. An entry may carry several tags. A password, a personal access token, and an API key are the same kind of entry. The secret lives in `password`.

Copy is on every row. It writes the secret to the clipboard and does not show it. Copy uses the unlock already done. The clipboard warning in §9 still applies.

Clicking a row opens that entry in a side panel. The panel shows the label, tags, username, URL, notes, and a masked secret, plus Copy, View, Edit, and Delete. Delete is visually quieter than the others.

- **View** is labeled View. It asks for Hello again, then shows the secret. The secret stays until the user selects another row, closes the panel, presses View again, the PC sleeps, or Windows locks. There is no countdown. The list never shows it. Covering the secret does not end the 24-hour unlock.
- **Create new** replaces the side panel with a blank entry. The list stays. Fields: label, username, secret, URL, notes, tags. Generate fills the secret using the `pwm generate` defaults (20 characters, symbols on). The user may paste a secret instead. There is no step that asks whether it is a password or a token. The secret stays visible until save, then it is masked.
- **Edit** uses those same fields, filled in. The secret stays masked unless the user presses View. Save does not ask for Hello again.
- **Delete** asks the user to type the label. The entry is removed only when it matches. Cancel leaves the entry. Delete does not ask for Hello again.

Copy, Create, Edit, and Delete do not ask for Hello again. The window is already unlocked.

If no vault exists, Signet tells the user to run `pwm init`. Signet does not grow a second way to create the first vault. `pwm change-master` stays a CLI command.

### 13.5 What this section does not change

- §§2–7 and the PWM1 layout stay the contract for `pwm`.
- Crypto primitives for the vault stay Argon2id and AES-GCM. Hello only unwraps a key.
- PRF must be exercised on this machine before Signet is called done. Unit tests mock the PRF output. They must show: a missing sidecar still opens with the master, a matching sidecar round-trips the vault key, a CLI salt rotation makes the sidecar fail closed until the master is typed, and a Signet save keeps the salt and uses a fresh nonce.

The window toolkit is an implementation choice. It must stay on this computer and must not open a port or a browser. Record the choice in LEARNINGS.md when it is made.

Initial version: 2026-06-14  
Updated 2026-08-16: added §7.0 landing page for bare `pwm` (PWM-R009).  
Updated 2026-08-16: added §7.11 `pwm backup` (PWM-R007). Copies ciphertext only; no decrypt.  
Updated 2026-10-28: added §13 Signet. The window uses the existing Windows Hello PIN. A PIN change in Windows needs nothing inside Signet. One Hello unlock lasts 24 hours. Launch is a Start menu shortcut, not `pwm`. No code yet.
