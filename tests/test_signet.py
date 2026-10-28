"""Signet list behavior. These tests do not call Windows Hello."""

import json

from pwm.crypto import ArgonParams, encrypt_vault
from pwm.hello import assert_layout
from pwm.models import Entry
from pwm.signet import SignetApp, entries_from_plaintext, filter_entries, sort_entries

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


def _texts(widget) -> list[str]:
    import tkinter as tk

    found: list[str] = []
    if isinstance(widget, tk.Label):
        found.append(str(widget.cget("text")))
    for child in widget.winfo_children():
        found.extend(_texts(child))
    return found
