"""
Signet window.

The list, Copy, the side panel, Create, Edit, and Delete, and the 24-hour
unlock. The Start menu shortcut is not in this slice. Typing ``pwm``
does not open this window.
Launch with ``python -m pwm.signet``.

The toolkit is tkinter. It is a normal window on this PC. It does not open
a port and it does not open a browser.
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import json
import os
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import font as tkfont

from pwm.clipboard import copy_to_clipboard
from pwm.crypto import (
    ArgonParams,
    VaultDecryptionError,
    decrypt_vault_with_key,
    derive_key,
    get_header_info,
    reencrypt_vault_with_key,
)
from pwm.generator import generate_password
from pwm.hello import HelloCancelled, HelloError, enroll, evaluate
from pwm.models import Entry, now_iso
from pwm.sidecar import (
    SidecarError,
    SidecarMismatch,
    build_sidecar,
    open_with_sidecar,
    parse_sidecar,
    read_sidecar,
    rewrite_sidecar,
    unwrap_vault_key,
    write_sidecar,
)
from pwm.vault import atomic_write, get_default_vault_path

BG = "#141414"
PANEL = "#1c1c1c"
TEXT = "#f3f1ea"
MUTED = "#9a958a"
BORDER = "#2e2e2e"
BRASS = "#d6a25e"
BRASS_INK = "#1a140c"
SELECTED = "#2a241c"
MASK = "••••••••••••"
UNLOCK_SECONDS = 24 * 60 * 60


def session_expired(started_at: float, now: float) -> bool:
    """True when 24 wall-clock hours have passed since Hello unlock.

    ``started_at`` and ``now`` are ``time.time()`` values. Sleep, lid close,
    and the Windows lock do not end the session by themselves. A monotonic
    clock pauses while Windows is suspended, so it would let a closed laptop
    stay unlocked for longer than a day of real time. Clicks do not move
    ``started_at``. Quitting the window drops it, and nothing writes it down.
    """
    return now - started_at >= UNLOCK_SECONDS


def entries_from_plaintext(plaintext: bytes) -> list[Entry]:
    """Read entries out of a decrypted vault. The secret stays on the entry."""
    data = _vault_object(plaintext)
    raw = data.get("entries", [])
    if not isinstance(raw, list):
        raise ValueError("Vault entries are not a list")
    return [Entry.from_dict(item) for item in raw]


def document_created_at(plaintext: bytes) -> str:
    """The vault document's created_at, kept stable across Signet saves."""
    created = _vault_object(plaintext).get("created_at")
    if isinstance(created, str) and created:
        return created
    return now_iso()


def plaintext_for(entries: list[Entry], created_at: str) -> bytes:
    data = {
        "version": 1,
        "created_at": created_at,
        "entries": [entry.to_dict() for entry in entries],
    }
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def parse_tags(text: str) -> list[str]:
    """Split a tags field on commas and whitespace. Order is kept. Duplicates drop."""
    tags: list[str] = []
    for part in text.replace(",", " ").split():
        if part not in tags:
            tags.append(part)
    return tags


def _blank(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def add_entry(
    entries: list[Entry],
    *,
    label: str,
    username: str,
    password: str,
    url: str,
    notes: str,
    tags: list[str],
) -> list[Entry]:
    clean = label.strip()
    if not clean:
        raise ValueError("A label is required.")
    if any(entry.label == clean for entry in entries):
        raise ValueError(f"An entry with label '{clean}' already exists.")
    created = Entry(
        id=str(uuid.uuid4()),
        label=clean,
        username=_blank(username),
        password=password,
        url=_blank(url),
        notes=_blank(notes),
        tags=tags,
    )
    return [*entries, created]


def replace_entry(
    entries: list[Entry],
    entry_id: str,
    *,
    label: str,
    username: str,
    password: str,
    url: str,
    notes: str,
    tags: list[str],
) -> list[Entry]:
    clean = label.strip()
    if not clean:
        raise ValueError("A label is required.")
    current = next((entry for entry in entries if entry.id == entry_id), None)
    if current is None:
        raise ValueError("That entry is no longer in the list.")
    if any(entry.label == clean and entry.id != entry_id for entry in entries):
        raise ValueError(f"An entry with label '{clean}' already exists.")
    updated: list[Entry] = []
    for entry in entries:
        if entry.id != entry_id:
            updated.append(entry)
            continue
        changed = Entry(
            id=entry.id,
            label=clean,
            username=_blank(username),
            password=password,
            url=_blank(url),
            notes=_blank(notes),
            tags=tags,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
        changed.touch()
        updated.append(changed)
    return updated


def delete_entry(entries: list[Entry], entry_id: str, typed_label: str) -> list[Entry]:
    current = next((entry for entry in entries if entry.id == entry_id), None)
    if current is None:
        raise ValueError("That entry is no longer in the list.")
    if typed_label != current.label:
        raise ValueError("Type the label exactly.")
    return [entry for entry in entries if entry.id != entry_id]


class VaultChangedError(VaultDecryptionError):
    """The file on disk no longer opens with the key this session holds."""


def save_unlocked(
    vault_path: Path,
    key: bytes,
    entries: list[Entry],
    *,
    created_at: str,
    prf_output: bytes | None,
) -> str | None:
    """Signet save. Same salt, fresh vault nonce, same vault key.

    When the PRF output is still in memory, the sidecar is rewritten with a
    fresh nonce and the same PRF salt. This does not ask for Hello and does
    not use the master password. The vault key is unchanged, so an old sidecar
    still unwraps the vault if the rewrite fails. The return value is a
    warning in that case, and None when the sidecar was refreshed or absent.

    The key must still decrypt the file. A CLI save rotates the salt and
    derives a new key. Writing the in-memory entries under that new salt
    with the old key would make the master password unable to open the vault.
    """
    if len(key) != 32:
        raise ValueError("Vault key must be 32 bytes")
    previous = Path(vault_path).read_bytes()
    try:
        decrypt_vault_with_key(previous, key)
    except VaultDecryptionError as exc:
        raise VaultChangedError(
            "The vault file changed outside Signet. The master password is required."
        ) from exc
    blob = reencrypt_vault_with_key(plaintext_for(entries, created_at), previous, key)
    atomic_write(Path(vault_path), blob)
    if not prf_output:
        return None
    try:
        side = read_sidecar(Path(vault_path))
        if side is None:
            return None
        write_sidecar(Path(vault_path), rewrite_sidecar(side, key, prf_output))
    except (OSError, SidecarError, ValueError):
        return "Saved the vault. The Hello file was not refreshed."
    return None


def _vault_object(plaintext: bytes) -> dict:
    data = json.loads(plaintext.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Vault plaintext is not an object")
    return data


def filter_entries(entries: list[Entry], text: str, tag: str | None) -> list[Entry]:
    """Match label, username, and tags. The secret is not part of the search."""
    query = text.casefold().strip()
    chosen = None if tag in (None, "", "All") else tag
    matched: list[Entry] = []
    for entry in entries:
        if chosen is not None and chosen not in entry.tags:
            continue
        if query:
            haystack = " ".join(
                [entry.label, entry.username or "", " ".join(entry.tags)]
            ).casefold()
            if query not in haystack:
                continue
        matched.append(entry)
    return matched


def sort_entries(entries: list[Entry], mode: str) -> list[Entry]:
    if mode == "Username":
        return sorted(entries, key=lambda entry: ((entry.username or "").casefold(), entry.label.casefold()))
    return sorted(entries, key=lambda entry: entry.label.casefold())


def workstation_locked() -> bool:
    """True when Windows has locked the desktop.

    OpenInputDesktop fails while the lock screen owns the input desktop.
    A revealed secret is covered. The vault key stays in memory.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenInputDesktop.restype = ctypes.c_void_p
    user32.OpenInputDesktop.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    user32.CloseDesktop.argtypes = [ctypes.c_void_p]
    handle = user32.OpenInputDesktop(0, False, 0x0001)
    if not handle:
        return True
    user32.CloseDesktop(handle)
    return False


def enable_dpi() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class SignetApp:
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = Path(vault_path)
        self.root: tk.Tk | None = None
        self.body: tk.Frame | None = None
        self.status: tk.Label | None = None
        self.master_entry: tk.Entry | None = None
        self.error_label: tk.Label | None = None
        self.entries: list[Entry] = []
        self.vault_key: bytes | None = None
        self.credential_id: bytes | None = None
        self.prf_salt: bytes | None = None
        self.prf_output: bytes | None = None
        self.created_at: str | None = None
        self.selected_id: str | None = None
        self.revealed_id: str | None = None
        self._mode = "entry"
        self._form_shown = False
        self._filter: tk.StringVar | None = None
        self._filter_trace: str | None = None
        self._sort: tk.StringVar | None = None
        self._tag = "All"
        self._last_tick = time.monotonic()
        self._unlocked_at: float | None = None
        self._expiring = False
        self._watch_job: str | None = None
        self._list_inner: tk.Frame | None = None
        self._secret_value: tk.Label | None = None
        self._panel: tk.Frame | None = None
        self.form_label: tk.Entry | None = None
        self.form_username: tk.Entry | None = None
        self.form_secret: tk.Entry | None = None
        self.form_url: tk.Entry | None = None
        self.form_notes: tk.Text | None = None
        self.form_tags: tk.Entry | None = None
        self.form_confirm: tk.Entry | None = None
        self._form_error: tk.Label | None = None

    def run(self) -> None:
        self.start()
        assert self.root is not None
        self.root.mainloop()

    def start(self) -> None:
        self._build()
        assert self.root is not None
        if not self.vault_path.is_file():
            self.show_no_vault()
            return
        if read_sidecar(self.vault_path) is None:
            self.show_master(
                "Type the master password once. Signet will then ask for the "
                "laptop PIN you already use to sign in. The password is not saved."
            )
            return
        self._set_status("Approve Windows Hello with your laptop PIN.")
        self.root.after(200, self.hello_unlock)

    def hwnd(self) -> int:
        assert self.root is not None
        self.root.update_idletasks()
        return int(self.root.winfo_id())

    def _build(self) -> None:
        root = _open_root()
        root.title("Signet")
        root.configure(bg=BG)
        root.geometry("980x640")
        root.minsize(760, 480)
        root.protocol("WM_DELETE_WINDOW", self.close)
        family = "Segoe UI" if "Segoe UI" in tkfont.families() else "TkDefaultFont"
        root.option_add("*Font", (family, 10))
        self.root = root
        self._filter = tk.StringVar(master=root)
        self._sort = tk.StringVar(master=root, value="Label")

        header = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x")
        tk.Label(header, text="Signet", bg=PANEL, fg=TEXT, font=(family, 14, "bold")).pack(
            anchor="w", padx=16, pady=10
        )

        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True)

        self.status = tk.Label(root, text="", bg=BG, fg=MUTED, anchor="w")
        self.status.pack(fill="x", padx=16, pady=(0, 10))
        self._watch_job = root.after(400, self._watch_desktop)

    def close(self) -> None:
        self.entries = []
        self.vault_key = None
        self.credential_id = None
        self.prf_salt = None
        self.prf_output = None
        self.created_at = None
        self.revealed_id = None
        self._form_shown = False
        self._unlocked_at = None
        if self.root is not None:
            if self._watch_job is not None:
                try:
                    self.root.after_cancel(self._watch_job)
                except tk.TclError:
                    pass
                self._watch_job = None
            self.root.destroy()
            self.root = None
        gc.collect()

    def _clear_body(self) -> None:
        assert self.body is not None
        for child in self.body.winfo_children():
            child.destroy()
        self.master_entry = None
        self.error_label = None
        self._list_inner = None
        self._secret_value = None
        self._panel = None
        self._forget_form()

    def _set_status(self, text: str) -> None:
        if self.status is not None:
            self.status.configure(text=text)

    def show_no_vault(self) -> None:
        self._clear_body()
        assert self.body is not None
        tk.Label(
            self.body,
            text="No vault yet.\n\nIn a terminal, run pwm init.\nSignet does not create the first vault.",
            bg=BG,
            fg=TEXT,
            justify="left",
        ).pack(anchor="w", padx=28, pady=28)
        self._set_status(str(self.vault_path))

    def show_master(self, message: str) -> None:
        self._clear_body()
        self.entries = []
        self.vault_key = None
        self.prf_output = None
        self.created_at = None
        self.revealed_id = None
        self._mode = "entry"
        self._unlocked_at = None
        assert self.body is not None
        wrap = tk.Frame(self.body, bg=BG)
        wrap.pack(anchor="w", padx=28, pady=28)
        tk.Label(wrap, text=message, bg=BG, fg=TEXT, wraplength=520, justify="left").pack(anchor="w")
        self.master_entry = tk.Entry(
            wrap,
            show="*",
            width=42,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BRASS,
        )
        self.master_entry.pack(anchor="w", pady=(16, 8), ipady=6)
        self.master_entry.focus_set()
        self.master_entry.bind("<Return>", lambda _event: self.submit_master())
        _button(wrap, "Continue", self.submit_master, primary=True).pack(anchor="w", pady=(8, 0))
        self.error_label = tk.Label(wrap, text="", bg=BG, fg=BRASS, wraplength=520, justify="left")
        self.error_label.pack(anchor="w", pady=(12, 0))
        self._set_status("The master password is the recovery key. It is not stored.")

    def show_cancelled(self) -> None:
        self._clear_body()
        self.entries = []
        self.vault_key = None
        self.prf_output = None
        self.created_at = None
        self.revealed_id = None
        self._mode = "entry"
        self._unlocked_at = None
        assert self.body is not None
        wrap = tk.Frame(self.body, bg=BG)
        wrap.pack(anchor="w", padx=28, pady=28)
        tk.Label(
            wrap,
            text="Hello was cancelled. No entries are shown.",
            bg=BG,
            fg=TEXT,
        ).pack(anchor="w")
        _button(wrap, "Try Hello again", self.hello_unlock, primary=True).pack(anchor="w", pady=(16, 8))
        _button(wrap, "Use master password", self._use_master).pack(anchor="w")

    def _use_master(self) -> None:
        self.show_master(
            "Type the master password. Signet will ask for the laptop PIN "
            "and refresh the Hello unlock for this vault."
        )

    def submit_master(self) -> None:
        if self.master_entry is None:
            return
        master = self.master_entry.get()
        self.master_entry.delete(0, "end")
        if not master:
            self._show_error("Type the master password.")
            return
        self._set_status("Unlocking…")
        assert self.root is not None
        self.root.update_idletasks()
        try:
            blob = self.vault_path.read_bytes()
            info = get_header_info(blob)
            if not info.get("valid"):
                raise VaultDecryptionError(
                    "Decryption failed. Wrong master password or the vault file is corrupted."
                )
            params = ArgonParams(info["time_cost"], info["memory_cost"], info["parallelism"])
            key = derive_key(master, bytes.fromhex(info["salt_hex"]), params)
            plaintext, _params = decrypt_vault_with_key(blob, key)
            entries = entries_from_plaintext(plaintext)
            created_at = document_created_at(plaintext)
        except (VaultDecryptionError, ValueError, json.JSONDecodeError, KeyError):
            self._show_error(
                "Decryption failed. Wrong master password or the vault file is corrupted."
            )
            self._set_status("")
            return
        finally:
            master = ""
        self._finish_with_key(key, entries, created_at)

    def _show_error(self, text: str) -> None:
        if self.error_label is not None:
            self.error_label.configure(text=text)

    def _finish_with_key(self, key: bytes, entries: list[Entry], created_at: str) -> None:
        """Hello-wrap the key we just derived, then show the list.

        The PRF output stays in memory for this session so a later save can
        refresh the sidecar. It is not the master password, and it is not written
        anywhere except inside that sidecar.
        """
        side = read_sidecar(self.vault_path)
        if side is not None:
            try:
                parsed = parse_sidecar(side)
                self._set_status("Approve Windows Hello with your laptop PIN.")
                assert self.root is not None
                self.root.update_idletasks()
                prf = evaluate(self.hwnd(), parsed.credential_id, parsed.prf_salt)
                try:
                    held = bytes(prf)
                    refreshed = rewrite_sidecar(side, key, prf)
                    write_sidecar(self.vault_path, refreshed)
                    self.credential_id = parsed.credential_id
                    self.prf_salt = bytes(parsed.prf_salt)
                finally:
                    del prf
                self._enter(key, entries, created_at, held)
                return
            except HelloCancelled:
                self.vault_key = None
                self.show_cancelled()
                return
            except HelloError:
                pass
            except SidecarError:
                pass

        prf_salt = os.urandom(32)
        self._set_status("Approve Windows Hello to finish setup. This uses your laptop PIN.")
        assert self.root is not None
        self.root.update_idletasks()
        try:
            credential_id, prf = enroll(self.hwnd(), prf_salt)
            try:
                held = bytes(prf)
                blob = build_sidecar(
                    key,
                    prf,
                    credential_id=credential_id,
                    prf_salt=prf_salt,
                )
                write_sidecar(self.vault_path, blob)
            finally:
                del prf
        except HelloCancelled:
            self.vault_key = None
            self.show_cancelled()
            return
        except (HelloError, OSError, ValueError) as exc:
            self.vault_key = None
            self.show_master(f"Windows Hello did not finish setup. {exc}")
            return
        self.credential_id = credential_id
        self.prf_salt = prf_salt
        self._enter(key, entries, created_at, held)

    def hello_unlock(self) -> None:
        side = read_sidecar(self.vault_path)
        if side is None:
            self.show_master(
                "Type the master password once. Signet will then ask for the "
                "laptop PIN you already use to sign in. The password is not saved."
            )
            return
        try:
            parsed = parse_sidecar(side)
            self._set_status("Approve Windows Hello with your laptop PIN.")
            assert self.root is not None
            self.root.update_idletasks()
            prf = evaluate(self.hwnd(), parsed.credential_id, parsed.prf_salt)
            try:
                blob = self.vault_path.read_bytes()
                plaintext = open_with_sidecar(blob, side, prf)
                key = unwrap_vault_key(side, prf)
                entries = entries_from_plaintext(plaintext)
                created_at = document_created_at(plaintext)
                held = bytes(prf)
            finally:
                del prf
        except HelloCancelled:
            self.show_cancelled()
            return
        except SidecarMismatch as exc:
            self.show_master(str(exc))
            return
        except (HelloError, SidecarError, VaultDecryptionError, json.JSONDecodeError, ValueError, OSError):
            self.show_master(
                "Signet could not open the vault with Windows Hello. Type the master password."
            )
            return
        self.credential_id = parsed.credential_id
        self.prf_salt = bytes(parsed.prf_salt)
        self._enter(key, entries, created_at, held)

    def _enter(
        self,
        key: bytes,
        entries: list[Entry],
        created_at: str,
        prf_output: bytes | None,
    ) -> None:
        self.vault_key = key
        self.entries = entries
        self.created_at = created_at
        self.prf_output = bytes(prf_output) if prf_output else None
        self.selected_id = entries[0].id if entries else None
        self.revealed_id = None
        self._mode = "entry"
        self._form_shown = False
        self._unlocked_at = time.time()
        self._tag = "All"
        self.show_list()

    def show_list(self) -> None:
        self._clear_body()
        assert self.body is not None
        list_side = tk.Frame(self.body, bg=BG)
        list_side.pack(side="left", fill="both", expand=True)
        self._panel = tk.Frame(self.body, bg=PANEL, width=320)
        self._panel.pack(side="right", fill="y")
        self._panel.pack_propagate(False)

        tools = tk.Frame(list_side, bg=BG)
        tools.pack(fill="x", padx=16, pady=(16, 8))
        assert self._filter is not None and self._sort is not None
        filter_box = tk.Entry(
            tools,
            textvariable=self._filter,
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BRASS,
        )
        filter_box.pack(side="left", fill="x", expand=True, ipady=6)
        if self._filter_trace is not None:
            self._filter.trace_remove("write", self._filter_trace)
        self._filter_trace = self._filter.trace_add("write", lambda *_args: self.refresh_rows())
        _button(tools, "Create new", self.start_create, primary=True).pack(side="right", padx=(8, 0))
        sort = tk.OptionMenu(tools, self._sort, "Label", "Username", command=lambda _value: self.refresh_rows())
        sort.configure(bg=PANEL, fg=MUTED, activebackground=PANEL, relief="flat", highlightthickness=0)
        sort.pack(side="right", padx=(8, 0))

        self._tags = tk.Frame(list_side, bg=BG)
        self._tags.pack(fill="x", padx=16, pady=(0, 8))

        canvas = tk.Canvas(list_side, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._list_inner = tk.Frame(canvas, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        window = canvas.create_window((0, 0), window=self._list_inner, anchor="nw")
        self._list_inner.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"))

        tk.Label(
            list_side,
            text="Copy leaves the secret on the clipboard. Other apps and Win+V can read it.",
            bg=BG,
            fg=MUTED,
            wraplength=560,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        self.refresh_rows()
        self._set_status(f"{len(self.entries)} entries")

    def refresh_rows(self) -> None:
        if self._list_inner is None:
            return
        if not self._expiring and self._session_is_over():
            self._later(self._expire_session)
            return
        for child in self._list_inner.winfo_children():
            child.destroy()
        self._render_tags()
        assert self._filter is not None and self._sort is not None
        visible = sort_entries(
            filter_entries(self.entries, self._filter.get(), self._tag),
            self._sort.get(),
        )
        if self._mode == "entry" and self.selected_id not in {entry.id for entry in visible}:
            self.selected_id = visible[0].id if visible else None
            self.revealed_id = None
        if not visible:
            tk.Label(self._list_inner, text="No matching entries", bg=PANEL, fg=MUTED).pack(
                anchor="w", padx=12, pady=12
            )
        for entry in visible:
            self._render_row(entry)
        if self._mode == "entry":
            self._render_panel()

    def _render_tags(self) -> None:
        assert hasattr(self, "_tags")
        for child in self._tags.winfo_children():
            child.destroy()
        tags = sorted({tag for entry in self.entries for tag in entry.tags})
        self._chip(self._tags, "All", self._tag == "All", lambda: self._choose_tag("All"))
        for tag in tags:
            self._chip(self._tags, tag, self._tag == tag, lambda name=tag: self._choose_tag(name))

    def _choose_tag(self, tag: str) -> None:
        self._tag = tag
        if self.root is not None:
            self.root.after_idle(self.refresh_rows)

    def _chip(self, parent: tk.Frame, text: str, selected: bool, command) -> None:
        label = tk.Label(
            parent,
            text=text,
            bg=BRASS if selected else BG,
            fg=BRASS_INK if selected else MUTED,
            padx=8,
            pady=2,
            cursor="hand2",
        )
        label.pack(side="left", padx=(0, 6))
        label.bind("<Button-1>", lambda _event: command())

    def _render_row(self, entry: Entry) -> None:
        assert self._list_inner is not None
        selected = entry.id == self.selected_id
        row = tk.Frame(self._list_inner, bg=SELECTED if selected else PANEL)
        row.pack(fill="x")
        text_side = tk.Frame(row, bg=row.cget("bg"))
        text_side.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        tk.Label(text_side, text=entry.label, bg=row.cget("bg"), fg=BRASS if selected else TEXT).pack(anchor="w")
        tk.Label(text_side, text=entry.username or "", bg=row.cget("bg"), fg=MUTED).pack(anchor="w")
        if entry.tags:
            tk.Label(text_side, text="  ".join(entry.tags), bg=row.cget("bg"), fg=MUTED).pack(anchor="w")
        copy = _button(row, "Copy", lambda entry_id=entry.id: self.copy_entry(entry_id), primary=True)
        copy.pack(side="right", padx=10, pady=8)

        def select(_event, entry_id=entry.id) -> None:
            self.select(entry_id)

        row.bind("<Button-1>", select)
        text_side.bind("<Button-1>", select)
        for child in text_side.winfo_children():
            child.bind("<Button-1>", select)

    def select(self, entry_id: str) -> None:
        if not self._ensure_unlocked():
            return
        if entry_id != self.revealed_id:
            self.revealed_id = None
        self.selected_id = entry_id
        self._mode = "entry"
        self._form_shown = False
        if self.root is not None:
            self.root.after_idle(self.refresh_rows)

    def _selected(self) -> Entry | None:
        for entry in self.entries:
            if entry.id == self.selected_id:
                return entry
        return None

    def _render_panel(self) -> None:
        if self._panel is None:
            return
        for child in self._panel.winfo_children():
            child.destroy()
        self._secret_value = None
        self._forget_form()
        if self._mode == "create":
            self._render_form(None)
        elif self._mode == "edit" and self._selected() is not None:
            self._render_form(self._selected())
        elif self._mode == "delete" and self._selected() is not None:
            self._render_delete()
        else:
            self._mode = "entry"
            self._render_entry()

    def _forget_form(self) -> None:
        self.form_label = None
        self.form_username = None
        self.form_secret = None
        self.form_url = None
        self.form_notes = None
        self.form_tags = None
        self.form_confirm = None
        self._form_error = None

    def _render_entry(self) -> None:
        assert self._panel is not None
        entry = self._selected()
        pad = tk.Frame(self._panel, bg=PANEL)
        pad.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(pad, text="OPEN ENTRY", bg=PANEL, fg=MUTED).pack(anchor="w")
        if entry is None:
            tk.Label(pad, text="Select an entry", bg=PANEL, fg=TEXT).pack(anchor="w", pady=(12, 0))
            return
        tk.Label(pad, text=entry.label, bg=PANEL, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(4, 8))
        if entry.tags:
            tk.Label(pad, text="  ".join(entry.tags), bg=PANEL, fg=BRASS).pack(anchor="w", pady=(0, 12))
        self._field(pad, "Username", entry.username or "—")
        self._field(pad, "URL", entry.url or "—")
        shown = entry.password if self.revealed_id == entry.id else MASK
        self._secret_value = self._field(pad, "Secret", shown)
        self._field(pad, "Notes", entry.notes or "—")
        actions = tk.Frame(pad, bg=PANEL)
        actions.pack(anchor="w", pady=(16, 0))
        _button(actions, "Copy", lambda: self.copy_entry(entry.id), primary=True).pack(side="left")
        _button(actions, "View", lambda: self.view_entry(entry.id)).pack(side="left", padx=(8, 0))
        _button(actions, "Edit", self.start_edit).pack(side="left", padx=(8, 0))
        _button(actions, "Delete", self.start_delete, quiet=True).pack(side="left", padx=(8, 0))

    def start_create(self) -> None:
        if not self._ensure_unlocked():
            return
        self._mode = "create"
        self.revealed_id = None
        self._later(self._render_panel)

    def start_edit(self) -> None:
        if not self._ensure_unlocked():
            return
        if self._selected() is None:
            return
        self._mode = "edit"
        self._later(self._render_panel)

    def start_delete(self) -> None:
        if not self._ensure_unlocked():
            return
        if self._selected() is None:
            return
        self._mode = "delete"
        self.revealed_id = None
        self._form_shown = False
        self._later(self._render_panel)

    def cancel_form(self) -> None:
        self._mode = "entry"
        self._form_shown = False
        self._later(self._render_panel)

    def _later(self, callback) -> None:
        """Run after the click returns, so Tk is not destroying the clicked widget."""
        if self.root is None:
            callback()
            return
        self.root.after_idle(callback)

    def _render_form(self, entry: Entry | None) -> None:
        assert self._panel is not None
        creating = entry is None
        pad = tk.Frame(self._panel, bg=PANEL)
        pad.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(pad, text="NEW ENTRY" if creating else "EDIT ENTRY", bg=PANEL, fg=MUTED).pack(anchor="w")
        self.form_label = self._form_entry(pad, "Label", "" if entry is None else entry.label)
        self.form_username = self._form_entry(pad, "Username", "" if entry is None else (entry.username or ""))
        secret = "" if entry is None else entry.password
        self._form_shown = creating or (entry is not None and self.revealed_id == entry.id)
        secret_row = tk.Frame(pad, bg=PANEL)
        secret_row.pack(fill="x")
        self.form_secret = self._form_entry(
            secret_row,
            "Secret",
            secret,
            show="" if self._form_shown else "*",
        )
        secret_actions = tk.Frame(pad, bg=PANEL)
        secret_actions.pack(anchor="w", pady=(6, 0))
        _button(secret_actions, "Generate", self.fill_generated).pack(side="left")
        if not creating:
            _button(secret_actions, "View", self.reveal_form_secret).pack(side="left", padx=(8, 0))
        self.form_url = self._form_entry(pad, "URL", "" if entry is None else (entry.url or ""))
        self.form_notes = self._form_notes(pad, "" if entry is None else (entry.notes or ""))
        self.form_tags = self._form_entry(
            pad,
            "Tags",
            "" if entry is None else " ".join(entry.tags),
        )
        tk.Label(
            pad,
            text="Separate tags with spaces or commas.",
            bg=PANEL,
            fg=MUTED,
        ).pack(anchor="w", pady=(4, 0))
        self._form_error = tk.Label(pad, text="", bg=PANEL, fg=BRASS, wraplength=270, justify="left")
        self._form_error.pack(anchor="w", pady=(8, 0))
        actions = tk.Frame(pad, bg=PANEL)
        actions.pack(anchor="w", pady=(12, 0))
        _button(actions, "Save", self.save_form, primary=True).pack(side="left")
        _button(actions, "Cancel", self.cancel_form).pack(side="left", padx=(8, 0))

    def _form_entry(self, parent: tk.Misc, caption: str, value: str, *, show: str = "") -> tk.Entry:
        tk.Label(parent, text=caption.upper(), bg=PANEL, fg=MUTED).pack(anchor="w", pady=(8, 2))
        entry = tk.Entry(
            parent,
            show=show,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BRASS,
        )
        entry.pack(fill="x", ipady=4)
        if value:
            entry.insert(0, value)
        return entry

    def _form_notes(self, parent: tk.Misc, value: str) -> tk.Text:
        tk.Label(parent, text="NOTES", bg=PANEL, fg=MUTED).pack(anchor="w", pady=(8, 2))
        box = tk.Text(
            parent,
            height=3,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BRASS,
            wrap="word",
        )
        box.pack(fill="x")
        if value:
            box.insert("1.0", value)
        return box

    def _show_form_error(self, text: str) -> None:
        if self._form_error is not None:
            self._form_error.configure(text=text)
        self._set_status(text)

    def fill_generated(self) -> None:
        if not self._ensure_unlocked():
            return
        if self.form_secret is None:
            return
        self.form_secret.delete(0, "end")
        self.form_secret.insert(0, generate_password())
        self.form_secret.configure(show="")
        self._form_shown = True

    def reveal_form_secret(self) -> None:
        if not self._ensure_unlocked():
            return
        if self.form_secret is None:
            return
        if self._form_shown:
            self.form_secret.configure(show="*")
            self._form_shown = False
            self.revealed_id = None
            self._set_status("Secret hidden")
            return
        if not self._confirm_view():
            return
        self.form_secret.configure(show="")
        self._form_shown = True
        if self.selected_id is not None:
            self.revealed_id = self.selected_id
        self._set_status("Secret shown until you leave it, lock Windows, or sleep.")

    def _form_values(self) -> tuple[str, str, str, str, str, list[str]]:
        assert self.form_label is not None
        assert self.form_username is not None
        assert self.form_secret is not None
        assert self.form_url is not None
        assert self.form_notes is not None
        assert self.form_tags is not None
        notes = self.form_notes.get("1.0", "end-1c")
        return (
            self.form_label.get(),
            self.form_username.get(),
            self.form_secret.get(),
            self.form_url.get(),
            notes,
            parse_tags(self.form_tags.get()),
        )

    def save_form(self) -> None:
        if not self._ensure_unlocked():
            return
        if self.vault_key is None or not self.created_at:
            self._show_form_error("Unlock the vault before saving.")
            return
        if self.form_label is None:
            return
        label, username, password, url, notes, tags = self._form_values()
        try:
            if self._mode == "create":
                updated = add_entry(
                    self.entries,
                    label=label,
                    username=username,
                    password=password,
                    url=url,
                    notes=notes,
                    tags=tags,
                )
                selected = updated[-1].id
            else:
                current = self._selected()
                if current is None:
                    self._show_form_error("That entry is no longer in the list.")
                    return
                updated = replace_entry(
                    self.entries,
                    current.id,
                    label=label,
                    username=username,
                    password=password,
                    url=url,
                    notes=notes,
                    tags=tags,
                )
                selected = current.id
        except ValueError as exc:
            self._show_form_error(str(exc))
            return
        self._write_entries(updated, selected=selected, success="Saved")

    def _render_delete(self) -> None:
        assert self._panel is not None
        entry = self._selected()
        assert entry is not None
        pad = tk.Frame(self._panel, bg=PANEL)
        pad.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(pad, text="DELETE ENTRY", bg=PANEL, fg=MUTED).pack(anchor="w")
        tk.Label(
            pad,
            text=f"Type {entry.label} to delete this entry.",
            bg=PANEL,
            fg=TEXT,
            wraplength=270,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))
        self.form_confirm = self._form_entry(pad, "Label", "")
        self._form_error = tk.Label(pad, text="", bg=PANEL, fg=BRASS, wraplength=270, justify="left")
        self._form_error.pack(anchor="w", pady=(8, 0))
        actions = tk.Frame(pad, bg=PANEL)
        actions.pack(anchor="w", pady=(12, 0))
        _button(actions, "Delete", self.confirm_delete, quiet=True).pack(side="left")
        _button(actions, "Cancel", self.cancel_form).pack(side="left", padx=(8, 0))

    def confirm_delete(self) -> None:
        if not self._ensure_unlocked():
            return
        entry = self._selected()
        if entry is None or self.form_confirm is None:
            return
        if self.vault_key is None or not self.created_at:
            self._show_form_error("Unlock the vault before saving.")
            return
        try:
            updated = delete_entry(self.entries, entry.id, self.form_confirm.get())
        except ValueError as exc:
            self._show_form_error(str(exc))
            return
        self._write_entries(
            updated,
            selected=updated[0].id if updated else None,
            success="Deleted",
        )

    def _write_entries(self, updated: list[Entry], *, selected: str | None, success: str) -> None:
        if self.vault_key is None or not self.created_at:
            self._show_form_error("Unlock the vault before saving.")
            return
        try:
            warning = save_unlocked(
                self.vault_path,
                self.vault_key,
                updated,
                created_at=self.created_at,
                prf_output=self.prf_output,
            )
        except VaultChangedError:
            self._later(self._vault_changed)
            return
        except (OSError, ValueError, VaultDecryptionError):
            self._show_form_error("Signet could not save the vault.")
            return
        self.entries = updated
        self.selected_id = selected
        self.revealed_id = None
        self._form_shown = False
        self._mode = "entry"
        self._set_status(warning or success)
        self._later(self.refresh_rows)

    def _vault_changed(self) -> None:
        """A CLI save rotated the key. Leave that file alone and ask for the master."""
        self.show_master(
            "The vault file changed outside Signet, so this edit was not saved. "
            "Type the master password to open the current file."
        )

    def _field(self, parent: tk.Frame, caption: str, value: str) -> tk.Label:
        tk.Label(parent, text=caption.upper(), bg=PANEL, fg=MUTED).pack(anchor="w", pady=(8, 0))
        label = tk.Label(parent, text=value, bg=PANEL, fg=TEXT, wraplength=270, justify="left")
        label.pack(anchor="w")
        return label

    def copy_entry(self, entry_id: str) -> None:
        if not self._ensure_unlocked():
            return
        entry = next((item for item in self.entries if item.id == entry_id), None)
        if entry is None or self.vault_key is None:
            return
        copy_to_clipboard(entry.password)
        self._set_status(f"Copied {entry.label}")

    def view_entry(self, entry_id: str) -> None:
        if not self._ensure_unlocked():
            return
        if self.revealed_id == entry_id:
            self.revealed_id = None
            self._render_panel()
            self._set_status("Secret hidden")
            return
        if not self._confirm_view():
            return
        self.revealed_id = entry_id
        self.selected_id = entry_id
        self._render_panel()
        self._set_status("Secret shown until you leave it, lock Windows, or sleep.")

    def _confirm_view(self) -> bool:
        """Ask Hello again. The session PRF used for saves stays as it was."""
        if self.credential_id is None or self.prf_salt is None:
            self._set_status("View needs Windows Hello, and this window has no passkey yet.")
            return False
        self._set_status("Approve Windows Hello to view this secret.")
        assert self.root is not None
        self.root.update_idletasks()
        try:
            prf = evaluate(self.hwnd(), self.credential_id, self.prf_salt)
            try:
                side = read_sidecar(self.vault_path)
                if side is None:
                    raise SidecarError("Sidecar could not be opened.")
                unwrap_vault_key(side, prf)
            finally:
                del prf
        except HelloCancelled:
            self._set_status("View cancelled. The secret stays hidden.")
            return False
        except (HelloError, SidecarError, OSError):
            self._set_status("Windows Hello did not show the secret.")
            return False
        return True

    def _session_is_over(self) -> bool:
        if self.vault_key is None or self._unlocked_at is None:
            return False
        return session_expired(self._unlocked_at, time.time())

    def _ensure_unlocked(self) -> bool:
        """False when this window has no vault key or the 24 hours have passed.

        A still-valid session is returned as-is. The deadline is not moved.
        """
        if self.vault_key is None or self._unlocked_at is None:
            return False
        if not session_expired(self._unlocked_at, time.time()):
            return True
        self._later(self._expire_session)
        return False

    def _expire_session(self) -> None:
        """Drop the key and ask Hello again. The master password is not the next step."""
        if self._expiring or self.vault_key is None:
            return
        self._expiring = True
        try:
            self.entries = []
            self.vault_key = None
            self.prf_output = None
            self.created_at = None
            self.revealed_id = None
            self._form_shown = False
            self._unlocked_at = None
            self._mode = "entry"
            self._clear_body()
            assert self.body is not None
            tk.Label(
                self.body,
                text="24 hours have passed. Signet needs the laptop PIN again.",
                bg=BG,
                fg=TEXT,
            ).pack(anchor="w", padx=28, pady=28)
            self.hello_unlock()
        finally:
            self._expiring = False

    def _watch_desktop(self) -> None:
        if self.root is None:
            return
        if not self._expiring and self._session_is_over():
            self._expire_session()
            if self.root is not None:
                self._watch_job = self.root.after(400, self._watch_desktop)
            return
        now = time.monotonic()
        slept = now - self._last_tick > 5
        self._last_tick = now
        showing = self.revealed_id is not None or self._form_shown
        locked = False
        if showing and not slept:
            try:
                locked = workstation_locked()
            except OSError:
                locked = False
        if showing and (slept or locked):
            self.revealed_id = None
            self._form_shown = False
            if self.form_secret is not None:
                self.form_secret.configure(show="*")
            elif self._mode == "entry":
                self._render_panel()
            self._set_status("Secret hidden")
        self._watch_job = self.root.after(400, self._watch_desktop)


def _open_root() -> tk.Tk:
    """Create the Tk root.

    On this PC, destroying one interpreter and creating another can fail for
    a moment with "couldn't read file init.tcl". The files are still there.
    Tcl reports Windows error 0 while the previous interpreter lets them go.
    A short retry gets past that. Opening Signet once does not hit it.
    """
    last: tk.TclError | None = None
    for attempt in range(6):
        try:
            return tk.Tk()
        except tk.TclError as exc:
            last = exc
            time.sleep(0.05 * (attempt + 1))
    assert last is not None
    raise last


def _button(parent: tk.Misc, text: str, command, primary: bool = False, quiet: bool = False) -> tk.Button:
    if primary:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=BRASS,
            fg=BRASS_INK,
            activebackground="#e0b56e",
            activeforeground=BRASS_INK,
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
        )
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=PANEL,
        fg=MUTED if quiet else TEXT,
        activebackground="#2a2a2a",
        activeforeground=MUTED if quiet else TEXT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        padx=12,
        pady=4,
        cursor="hand2",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="signet",
        description="Signet, the desktop window for a pwm vault.",
    )
    parser.add_argument(
        "--vault-path",
        type=Path,
        default=None,
        help="Vault file. Defaults to the same path pwm uses.",
    )
    args = parser.parse_args(argv)
    enable_dpi()
    app = SignetApp(args.vault_path or get_default_vault_path())
    app.run()


if __name__ == "__main__":
    main()
