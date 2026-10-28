"""Signet window behavior. These tests do not call Windows Hello."""

import json
import time

import pytest

from pwm.crypto import (
    ArgonParams,
    VaultDecryptionError,
    decrypt_vault,
    derive_key,
    encrypt_vault,
    get_header_info,
)
from pwm.hello import HelloCancelled, assert_layout
from pwm.models import Entry
from pwm.sidecar import (
    build_sidecar,
    parse_sidecar,
    read_sidecar,
    unwrap_vault_key,
    write_sidecar,
)
from pwm.signet import (
    MASK,
    UNLOCK_SECONDS,
    SignetApp,
    VaultChangedError,
    add_entry,
    delete_entry,
    entries_from_plaintext,
    filter_entries,
    parse_tags,
    replace_entry,
    save_unlocked,
    session_expired,
    sort_entries,
)

TINY = ArgonParams(time_cost=1, memory_cost=8, parallelism=1)


def _entry(label: str, **kwargs) -> Entry:
    return Entry(id=label, label=label, **kwargs)


def test_filter_ignores_the_secret_and_matches_a_tag():
    mail = _entry("Mail", username="ada", password="unique-secret-xyz", tags=["email", "work"])
    git = _entry("GitHub", username="ada", password="other", tags=["token"])

    assert filter_entries([mail, git], "unique-secret-xyz", None) == []
    assert filter_entries([mail, git], "ada", None) == [mail, git]
    assert filter_entries([mail, git], "", "work") == [mail]
    assert filter_entries([mail, git], "git", "token") == [git]
    assert filter_entries([mail, git], "mail", "token") == []


def test_sort_by_label_and_username():
    entries = [
        _entry("Zed", username="b"),
        _entry("Ada", username="c"),
        _entry("Bea", username="a"),
    ]
    assert [entry.label for entry in sort_entries(entries, "Label")] == ["Ada", "Bea", "Zed"]
    assert [entry.label for entry in sort_entries(entries, "Username")] == ["Bea", "Zed", "Ada"]


def test_entries_from_plaintext_roundtrip():
    payload = {
        "version": 1,
        "entries": [
            {
                "id": "1",
                "label": "Mail",
                "username": "ada",
                "password": "secret",
                "tags": ["email"],
            }
        ],
    }
    entries = entries_from_plaintext(json.dumps(payload).encode())
    assert entries[0].label == "Mail"
    assert entries[0].password == "secret"
    assert entries[0].tags == ["email"]


def test_webauthn_struct_layout_matches_the_header():
    assert_layout()


def test_missing_vault_tells_the_user_to_init(tmp_path):
    app = SignetApp(tmp_path / "vault")
    app.start()
    try:
        texts = _texts(app.root)
        assert any("pwm init" in text for text in texts)
        assert app.master_entry is None
    finally:
        app.close()


def test_vault_without_sidecar_asks_for_the_master_and_not_hello(tmp_path, monkeypatch):
    path = tmp_path / "vault"
    path.write_bytes(encrypt_vault(b'{"version":1,"entries":[]}', "pw", TINY))

    def fail(*_args, **_kwargs):
        raise AssertionError("Hello should wait until the master is accepted")

    monkeypatch.setattr("pwm.signet.enroll", fail)
    monkeypatch.setattr("pwm.signet.evaluate", fail)
    app = SignetApp(path)
    app.start()
    try:
        assert app.master_entry is not None
        app.master_entry.insert(0, "wrong")
        app.submit_master()
        texts = _texts(app.root)
        assert any("Wrong master password" in text for text in texts)
    finally:
        app.close()


def test_tags_labels_and_delete_rules():
    assert parse_tags("email, work email") == ["email", "work"]
    with pytest.raises(ValueError, match="required"):
        add_entry([], label="  ", username="", password="", url="", notes="", tags=[])
    mail = Entry(id="1", label="Mail", password="secret", created_at="t0", updated_at="t0")
    with pytest.raises(ValueError, match="already exists"):
        add_entry([mail], label="Mail", username="", password="x", url="", notes="", tags=[])
    with pytest.raises(ValueError, match="exactly"):
        delete_entry([mail], "1", "mail")
    assert delete_entry([mail], "1", "Mail") == []
    replaced = replace_entry(
        [mail],
        "1",
        label="Mail",
        username="ada",
        password="next",
        url="",
        notes="",
        tags=["email"],
    )
    assert replaced[0].id == "1"
    assert replaced[0].created_at == "t0"
    assert replaced[0].username == "ada"
    assert replaced[0].password == "next"
    assert replaced[0].tags == ["email"]


def test_signet_save_keeps_salt_and_updates_entries(tmp_path):
    path = tmp_path / "vault"
    created = "2020-01-01T00:00:00Z"
    blob = encrypt_vault(
        json.dumps({"version": 1, "created_at": created, "entries": []}).encode(),
        "pw",
        TINY,
    )
    path.write_bytes(blob)
    info = get_header_info(blob)
    key = derive_key("pw", bytes.fromhex(info["salt_hex"]), TINY)
    prf = b"\x11" * 32
    prf_salt = b"\x22" * 32
    side = build_sidecar(key, prf, credential_id=b"cred", prf_salt=prf_salt)
    write_sidecar(path, side)

    saved_entries = add_entry(
        [],
        label="Mail",
        username="ada",
        password="secret",
        url="",
        notes="",
        tags=["email", "work"],
    )
    assert save_unlocked(path, key, saved_entries, created_at=created, prf_output=prf) is None

    saved = path.read_bytes()
    saved_info = get_header_info(saved)
    assert saved_info["salt_hex"] == info["salt_hex"]
    assert saved_info["nonce_hex"] != info["nonce_hex"]
    data = json.loads(decrypt_vault(saved, "pw")[0])
    assert data["created_at"] == created
    assert data["entries"][0]["label"] == "Mail"
    assert data["entries"][0]["password"] == "secret"
    assert data["entries"][0]["username"] == "ada"
    assert data["entries"][0]["tags"] == ["email", "work"]
    with pytest.raises(VaultDecryptionError):
        decrypt_vault(saved, "wrong")
    new_side = read_sidecar(path)
    assert new_side is not None
    assert unwrap_vault_key(new_side, prf) == key
    assert parse_sidecar(new_side).prf_salt == prf_salt
    assert parse_sidecar(new_side).nonce != parse_sidecar(side).nonce


def test_save_refuses_when_the_cli_rotated_the_salt(tmp_path):
    path = tmp_path / "vault"
    created = "2020-01-01T00:00:00Z"
    blob = encrypt_vault(
        json.dumps({"version": 1, "created_at": created, "entries": []}).encode(),
        "pw",
        TINY,
    )
    path.write_bytes(blob)
    info = get_header_info(blob)
    key = derive_key("pw", bytes.fromhex(info["salt_hex"]), TINY)
    prf = b"\x11" * 32
    write_sidecar(path, build_sidecar(key, prf, credential_id=b"cred", prf_salt=b"\x22" * 32))
    side_before = read_sidecar(path)

    rotated_plain = json.dumps(
        {"version": 1, "created_at": created, "entries": [{"id": "9", "label": "From CLI", "password": "kept"}]}
    ).encode()
    rotated = encrypt_vault(rotated_plain, "pw", TINY)
    path.write_bytes(rotated)

    with pytest.raises(VaultChangedError):
        save_unlocked(
            path,
            key,
            [],
            created_at=created,
            prf_output=prf,
        )

    assert path.read_bytes() == rotated
    assert decrypt_vault(path.read_bytes(), "pw")[0] == rotated_plain
    assert read_sidecar(path) == side_before
    with pytest.raises(VaultDecryptionError):
        decrypt_vault(path.read_bytes(), "wrong")


def test_open_window_asks_for_the_master_when_the_file_changed(tmp_path, monkeypatch):
    app, path, _info = _open_unlocked(tmp_path, monkeypatch, [])
    try:
        rotated = encrypt_vault(
            b'{"version":1,"created_at":"2020-01-01T00:00:00Z","entries":[]}',
            "pw",
            TINY,
        )
        path.write_bytes(rotated)
        app.start_create()
        assert app.root is not None
        app.root.update()
        assert app.form_label is not None
        app.form_label.insert(0, "Mail")
        app.save_form()
        app.root.update()
        assert app.vault_key is None
        assert app.master_entry is not None
        assert path.read_bytes() == rotated
        assert any("master password" in text for text in _texts(app.root))
    finally:
        app.close()


def test_create_saves_without_asking_hello(tmp_path, monkeypatch):
    app, path, info = _open_unlocked(tmp_path, monkeypatch, [])
    try:
        app.start_create()
        assert app.root is not None
        app.root.update()
        assert app.form_label is not None
        assert app.form_secret is not None
        assert app.form_tags is not None
        assert app.form_secret.cget("show") == ""
        app.form_label.insert(0, "Mail")
        app.form_secret.insert(0, "secret")
        app.form_tags.insert(0, "email, work")
        assert app._filter is not None
        app._filter.set("nope")
        assert app.form_label.get() == "Mail"
        app._filter.set("")
        app.save_form()
        app.root.update()
        assert app._mode == "entry"
        saved = path.read_bytes()
        saved_info = get_header_info(saved)
        assert saved_info["salt_hex"] == info["salt_hex"]
        assert saved_info["nonce_hex"] != info["nonce_hex"]
        data = json.loads(decrypt_vault(saved, "pw")[0])
        assert data["entries"][0]["label"] == "Mail"
        assert data["entries"][0]["password"] == "secret"
        assert data["entries"][0]["tags"] == ["email", "work"]
        texts = _texts(app.root)
        assert "secret" not in texts
        assert MASK in texts
    finally:
        app.close()


def test_edit_keeps_the_secret_masked_and_delete_needs_the_label(tmp_path, monkeypatch):
    mail = Entry(id="1", label="Mail", username="ada", password="secret", tags=["email"])
    app, path, info = _open_unlocked(tmp_path, monkeypatch, [mail])
    try:
        app.start_edit()
        assert app.root is not None
        app.root.update()
        assert app.form_secret is not None
        assert app.form_secret.get() == "secret"
        assert app.form_secret.cget("show") == "*"
        app.fill_generated()
        assert len(app.form_secret.get()) == 20
        assert app.form_secret.cget("show") == ""
        app.form_secret.delete(0, "end")
        app.form_secret.insert(0, "next-secret")
        app.save_form()
        app.root.update()
        data = json.loads(decrypt_vault(path.read_bytes(), "pw")[0])
        assert data["entries"][0]["id"] == "1"
        assert data["entries"][0]["password"] == "next-secret"
        assert data["created_at"] == "2020-01-01T00:00:00Z"
        texts = _texts(app.root)
        assert "next-secret" not in texts
        assert MASK in texts

        nonce = get_header_info(path.read_bytes())["nonce_hex"]
        app.start_delete()
        app.root.update()
        assert app.form_confirm is not None
        app.form_confirm.insert(0, "mail")
        app.confirm_delete()
        assert app._mode == "delete"
        assert get_header_info(path.read_bytes())["nonce_hex"] == nonce
        app.form_confirm.delete(0, "end")
        app.form_confirm.insert(0, "Mail")
        app.confirm_delete()
        app.root.update()
        assert app.entries == []
        assert json.loads(decrypt_vault(path.read_bytes(), "pw")[0])["entries"] == []
        assert get_header_info(path.read_bytes())["salt_hex"] == info["salt_hex"]
    finally:
        app.close()


def test_session_clock_is_twenty_four_wall_clock_hours():
    start = 1_700_000_000.0
    assert UNLOCK_SECONDS == 24 * 60 * 60
    assert not session_expired(start, start + UNLOCK_SECONDS - 1)
    assert session_expired(start, start + UNLOCK_SECONDS)


def test_activity_does_not_extend_the_clock_and_expiry_asks_hello(tmp_path, monkeypatch):
    mail = Entry(id="1", label="Mail", password="secret")
    app, path, _info = _open_unlocked(tmp_path, monkeypatch, [mail])
    try:
        copied: list[str] = []
        monkeypatch.setattr("pwm.signet.copy_to_clipboard", lambda text: copied.append(text))
        started = app._unlocked_at
        assert started is not None
        app.copy_entry("1")
        assert copied == ["secret"]
        assert app._unlocked_at == started
        app._unlocked_at = time.time() - (UNLOCK_SECONDS - 30)
        assert app._ensure_unlocked() is True
        assert app.vault_key is not None

        asked: list[str] = []

        def cancel(*_args, **_kwargs):
            asked.append("hello")
            raise HelloCancelled

        monkeypatch.setattr("pwm.signet.evaluate", cancel)
        before = path.read_bytes()
        app._unlocked_at = time.time() - UNLOCK_SECONDS
        assert app._ensure_unlocked() is False
        assert app.root is not None
        app.root.update()
        assert asked == ["hello"]
        assert app.vault_key is None
        assert app.prf_output is None
        assert app.entries == []
        assert app._unlocked_at is None
        assert app.master_entry is None
        assert path.read_bytes() == before
        assert any("cancelled" in text.casefold() for text in _texts(app.root))
    finally:
        app.close()
        assert app.vault_key is None
        assert app._unlocked_at is None


def test_sleep_covers_a_revealed_secret_and_keeps_the_session(tmp_path, monkeypatch):
    mail = Entry(id="1", label="Mail", password="secret")
    app, _path, _info = _open_unlocked(tmp_path, monkeypatch, [mail])
    try:
        started = app._unlocked_at
        app.revealed_id = mail.id
        app._last_tick = time.monotonic() - 30
        app._watch_desktop()
        assert app.revealed_id is None
        assert app.vault_key is not None
        assert app._unlocked_at == started
        assert app.entries[0].password == "secret"
    finally:
        app.close()


def _open_unlocked(tmp_path, monkeypatch, entries: list[Entry]):
    path = tmp_path / "vault"
    created = "2020-01-01T00:00:00Z"
    payload = {
        "version": 1,
        "created_at": created,
        "entries": [entry.to_dict() for entry in entries],
    }
    blob = encrypt_vault(json.dumps(payload, separators=(",", ":")).encode(), "pw", TINY)
    path.write_bytes(blob)
    info = get_header_info(blob)
    key = derive_key("pw", bytes.fromhex(info["salt_hex"]), TINY)
    prf = b"\x33" * 32
    write_sidecar(
        path,
        build_sidecar(key, prf, credential_id=b"cred", prf_salt=b"\x44" * 32),
    )

    def fail(*_args, **_kwargs):
        raise AssertionError("Hello must not run")

    monkeypatch.setattr("pwm.signet.enroll", fail)
    monkeypatch.setattr("pwm.signet.evaluate", fail)
    app = SignetApp(path)
    app._build()
    app._enter(key, list(entries), created, prf)
    return app, path, info


def _texts(widget) -> list[str]:
    import tkinter as tk

    found: list[str] = []
    if isinstance(widget, tk.Label):
        found.append(str(widget.cget("text")))
    for child in widget.winfo_children():
        found.extend(_texts(child))
    return found
