"""
Integration tests for the Vault layer (uses real crypto underneath).

These tests exercise atomic writes, unlock/create, CRUD, search, and change-master.
They must run with a temp vault path so they never touch the user's real data.
"""

import tempfile
from pathlib import Path

import pytest

from pwm.vault import Vault
from pwm.crypto import VaultDecryptionError


def _temp_vault() -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".vault-test")
    tmp.close()
    p = Path(tmp.name)
    # We will delete the file at the end; Vault will write its own path
    p.unlink(missing_ok=True)
    return p


def test_create_unlock_add_list_search_delete(tmp_path: Path):
    vault_file = tmp_path / "vault"
    v = Vault(vault_file)

    assert not v.exists()
    v.create("master123")
    assert v.exists()
    assert v.is_unlocked()

    # Add a couple entries
    e1 = v.add("Gmail", username="alice@gmail.com", password="s3cr3t", tags=["email"])
    e2 = v.add("GitHub", username="alice", password="gh-pass", url="https://github.com")

    assert len(v.list_all()) == 2

    # Get exact
    got = v.get("Gmail")
    assert got is not None
    assert got.password == "s3cr3t"

    # Search
    results = v.search("alice")
    assert len(results) == 2

    results = v.search("github")
    assert len(results) == 1

    # Delete
    assert v.delete("Gmail") is True
    assert v.get("Gmail") is None
    assert len(v.list_all()) == 1

    # Lock and re-unlock with correct master
    v.lock()
    assert not v.is_unlocked()
    v.unlock("master123")
    assert v.is_unlocked()
    assert len(v.list_all()) == 1


def test_wrong_master_on_unlock(tmp_path: Path):
    vault_file = tmp_path / "vault"
    v = Vault(vault_file)
    v.create("correct")

    v.lock()
    with pytest.raises(VaultDecryptionError):
        v.unlock("wrong")


def test_cannot_add_duplicate_label(tmp_path: Path):
    v = Vault(tmp_path / "v")
    v.create("m")
    v.add("Netflix", password="net")

    with pytest.raises(ValueError):
        v.add("Netflix", password="net2")


def test_change_master_allows_unlock_with_new_only(tmp_path: Path):
    vault_file = tmp_path / "vault"
    v = Vault(vault_file)
    v.create("oldmaster")
    v.add("Work", password="workpw")

    v.change_master("newmaster")

    v.lock()
    with pytest.raises(VaultDecryptionError):
        v.unlock("oldmaster")

    v.unlock("newmaster")
    assert v.get("Work").password == "workpw"  # type: ignore[union-attr]


def test_atomic_write_on_save(tmp_path: Path):
    """We mainly verify that after save the file exists and can be unlocked again."""
    vault_file = tmp_path / "vault"
    v = Vault(vault_file)
    v.create("m")
    v.add("Label", password="p")

    # Force a re-save by touching an entry via update (or just save again)
    v.save()

    # Re-open from disk
    v2 = Vault(vault_file)
    v2.unlock("m")
    assert v2.get("Label").password == "p"  # type: ignore[union-attr]
