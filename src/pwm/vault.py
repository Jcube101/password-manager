"""
Vault storage layer.

Manages:
- Location (platformdirs or explicit path)
- Atomic writes
- Unlock (derive + decrypt)
- In-memory Entry list
- All CRUD + search
- Re-encryption on save / master change

Follows the contracts in SPEC.md exactly.
"""

from __future__ import annotations

import gc
import json
import os
import uuid
from pathlib import Path
from typing import Any

import platformdirs

from .crypto import (
    encrypt_vault,
    decrypt_vault,
    VaultDecryptionError,
    ArgonParams,
    get_header_info,
)
from .models import Entry, now_iso


DEFAULT_APP_NAME = "pwm"
DEFAULT_VAULT_FILENAME = "vault"


def get_default_vault_path() -> Path:
    """Return the platform-correct location for the vault file."""
    data_dir = platformdirs.user_data_dir(DEFAULT_APP_NAME)
    return Path(data_dir) / DEFAULT_VAULT_FILENAME


class Vault:
    """High-level vault manager. Most CLI commands will use an instance of this."""

    def __init__(self, vault_path: Path | str | None = None):
        if vault_path is None:
            self.vault_path = get_default_vault_path()
        else:
            self.vault_path = Path(vault_path)

        self._master: str | None = None
        self._entries: list[Entry] = []
        self._unlocked = False
        self._params_used: ArgonParams | None = None

    # ------------------------------------------------------------------
    # State & existence
    # ------------------------------------------------------------------

    def exists(self) -> bool:
        return self.vault_path.exists() and self.vault_path.is_file()

    def is_unlocked(self) -> bool:
        return self._unlocked

    def lock(self) -> None:
        """Best-effort clear of sensitive material from this process."""
        self._master = None
        self._entries = []
        self._unlocked = False
        self._params_used = None
        gc.collect()

    # ------------------------------------------------------------------
    # Unlock / create
    # ------------------------------------------------------------------

    def unlock(self, master: str) -> None:
        """Unlock an existing vault. Raises VaultDecryptionError on failure."""
        if not self.exists():
            raise FileNotFoundError(f"Vault does not exist at {self.vault_path}")

        blob = self.vault_path.read_bytes()
        plaintext, params = decrypt_vault(blob, master)

        data = json.loads(plaintext.decode("utf-8"))
        entries = [Entry.from_dict(e) for e in data.get("entries", [])]

        self._master = master
        self._entries = entries
        self._unlocked = True
        self._params_used = params

    def create(self, master: str) -> None:
        """Create a brand new empty vault. Fails if one already exists."""
        if self.exists():
            raise FileExistsError(f"Vault already exists at {self.vault_path}")

        self.vault_path.parent.mkdir(parents=True, exist_ok=True)

        initial = {
            "version": 1,
            "created_at": now_iso(),
            "entries": [],
        }
        plaintext = json.dumps(initial, separators=(",", ":")).encode("utf-8")

        blob = encrypt_vault(plaintext, master)
        self._atomic_write(blob)

        # Immediately unlock so the caller can start adding entries
        self._master = master
        self._entries = []
        self._unlocked = True
        self._params_used = None  # will be read on next load if needed

    # ------------------------------------------------------------------
    # Save (always re-encrypts with fresh salt/nonce)
    # ------------------------------------------------------------------

    def _atomic_write(self, blob: bytes) -> None:
        """Write blob to disk atomically using a sibling .tmp file."""
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.vault_path.with_suffix(self.vault_path.suffix + ".tmp")

        # Write + flush
        with open(tmp_path, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace (works on Windows and POSIX when on same filesystem)
        os.replace(tmp_path, self.vault_path)

    def save(self) -> None:
        """Serialize current in-memory state and write an encrypted blob."""
        if not self._unlocked or self._master is None:
            raise RuntimeError("Cannot save: vault is locked")

        data = {
            "version": 1,
            "created_at": self._entries[0].created_at if self._entries else now_iso(),
            "entries": [e.to_dict() for e in self._entries],
        }
        plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")

        blob = encrypt_vault(plaintext, self._master)
        self._atomic_write(blob)

        # Best-effort clear of the plaintext we just built
        del plaintext
        gc.collect()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def _require_unlocked(self) -> None:
        if not self._unlocked:
            raise RuntimeError("Vault is locked. Call unlock() first.")

    def add(
        self,
        label: str,
        *,
        username: str | None = None,
        password: str = "",
        url: str | None = None,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> Entry:
        self._require_unlocked()

        if any(e.label == label for e in self._entries):
            raise ValueError(f"An entry with label '{label}' already exists")

        entry = Entry(
            id=str(uuid.uuid4()),
            label=label,
            username=username,
            password=password,
            url=url,
            notes=notes,
            tags=tags or [],
        )
        self._entries.append(entry)
        self.save()
        return entry

    def get(self, label: str) -> Entry | None:
        self._require_unlocked()
        for e in self._entries:
            if e.label == label:
                return e
        return None

    def search(self, query: str) -> list[Entry]:
        self._require_unlocked()
        if not query:
            return list(self._entries)

        q = query.lower()
        results: list[Entry] = []
        for e in self._entries:
            haystack = " ".join(
                filter(
                    None,
                    [
                        e.label,
                        e.username or "",
                        e.url or "",
                        e.notes or "",
                        " ".join(e.tags),
                    ],
                )
            ).lower()
            if q in haystack:
                results.append(e)
        return results

    def list_all(self) -> list[Entry]:
        self._require_unlocked()
        return list(self._entries)

    def delete(self, label: str) -> bool:
        self._require_unlocked()
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.label != label]
        if len(self._entries) != before:
            self.save()
            return True
        return False

    def update(self, label: str, **changes: Any) -> Entry:
        """Update fields on an entry. Supports renaming via new_label if provided."""
        self._require_unlocked()
        entry = self.get(label)
        if entry is None:
            raise ValueError(f"No entry with label '{label}'")

        new_label = changes.pop("new_label", None)
        if new_label is not None and new_label != label:
            if any(e.label == new_label for e in self._entries):
                raise ValueError(f"Cannot rename: label '{new_label}' already exists")
            entry.label = new_label

        for field, value in changes.items():
            if hasattr(entry, field):
                setattr(entry, field, value)
            else:
                raise ValueError(f"Unknown field '{field}' for Entry")

        entry.touch()
        self.save()
        return entry

    # ------------------------------------------------------------------
    # Master password change (re-encrypts everything)
    # ------------------------------------------------------------------

    def change_master(self, new_master: str) -> None:
        """Change the master password. Re-derives and re-encrypts with fresh salt/nonce."""
        self._require_unlocked()
        if not new_master:
            raise ValueError("New master password cannot be empty")

        old_master = self._master
        self._master = new_master
        try:
            self.save()
        except Exception:
            # Roll back on any failure so the vault is not left in a bad state
            self._master = old_master
            raise

        # Best effort clear of the old reference
        old_master = None
        gc.collect()

    # ------------------------------------------------------------------
    # Introspection (for future `pwm inspect` or debugging)
    # ------------------------------------------------------------------

    def inspect_header(self) -> dict:
        """Read header information without unlocking (safe to call on locked vault)."""
        if not self.exists():
            return {"exists": False}
        blob = self.vault_path.read_bytes()
        info = get_header_info(blob)
        info["path"] = str(self.vault_path)
        info["exists"] = True
        return info
