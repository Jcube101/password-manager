"""
Signet window.

The list, Copy, and the side panel. Create, Edit, Delete, and the 24-hour
clock are not in this slice. Typing ``pwm`` does not open this window.
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
from pathlib import Path
from tkinter import font as tkfont

from pwm.clipboard import copy_to_clipboard
from pwm.crypto import (
    ArgonParams,
    VaultDecryptionError,
    decrypt_vault_with_key,
    derive_key,
    get_header_info,
)
from pwm.hello import HelloCancelled, HelloError, enroll, evaluate
from pwm.models import Entry
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
from pwm.vault import get_default_vault_path

BG = "#141414"
PANEL = "#1c1c1c"
TEXT = "#f3f1ea"
MUTED = "#9a958a"
BORDER = "#2e2e2e"
BRASS = "#d6a25e"
BRASS_INK = "#1a140c"
SELECTED = "#2a241c"
MASK = "••••••••••••"


def entries_from_plaintext(plaintext: bytes) -> list[Entry]:
    """Read entries out of a decrypted vault. The secret stays on the entry."""
    data = json.loads(plaintext.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Vault plaintext is not an object")
    raw = data.get("entries", [])
    if not isinstance(raw, list):
        raise ValueError("Vault entries are not a list")
    return [Entry.from_dict(item) for item in raw]


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
        self.selected_id: str | None = None
        self.revealed_id: str | None = None
        self._filter: tk.StringVar | None = None
        self._sort: tk.StringVar | None = None
        self._tag = "All"
        self._last_tick = time.monotonic()
        self._list_inner: tk.Frame | None = None
        self._secret_value: tk.Label | None = None
        self._panel: tk.Frame | None = None

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
        root = tk.Tk()
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
        root.after(400, self._watch_desktop)

    def close(self) -> None:
        self.entries = []
        self.vault_key = None
        self.credential_id = None
        self.prf_salt = None
        self.revealed_id = None
        gc.collect()
        if self.root is not None:
            self.root.destroy()
            self.root = None

    def _clear_body(self) -> None:
        assert self.body is not None
        for child in self.body.winfo_children():
            child.destroy()
        self.master_entry = None
        self.error_label = None
        self._list_inner = None
        self._secret_value = None
        self._panel = None

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
        self.revealed_id = None
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
        self.revealed_id = None
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
        except (VaultDecryptionError, ValueError, json.JSONDecodeError, KeyError):
            self._show_error(
                "Decryption failed. Wrong master password or the vault file is corrupted."
            )
            self._set_status("")
            return
        finally:
            master = ""
        self._finish_with_key(key, entries)

    def _show_error(self, text: str) -> None:
        if self.error_label is not None:
            self.error_label.configure(text=text)

    def _finish_with_key(self, key: bytes, entries: list[Entry]) -> None:
        """Hello-wrap the key we just derived, then show the list."""
        side = read_sidecar(self.vault_path)
        if side is not None:
            try:
                parsed = parse_sidecar(side)
                self._set_status("Approve Windows Hello with your laptop PIN.")
                assert self.root is not None
                self.root.update_idletasks()
                prf = evaluate(self.hwnd(), parsed.credential_id, parsed.prf_salt)
                try:
                    refreshed = rewrite_sidecar(side, key, prf)
                    write_sidecar(self.vault_path, refreshed)
                    self.credential_id = parsed.credential_id
                    self.prf_salt = bytes(parsed.prf_salt)
                finally:
                    del prf
                self._enter(key, entries)
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
        self._enter(key, entries)

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
        self._enter(key, entries)

    def _enter(self, key: bytes, entries: list[Entry]) -> None:
        self.vault_key = key
        self.entries = entries
        self.selected_id = entries[0].id if entries else None
        self.revealed_id = None
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
        self._filter.trace_add("write", lambda *_args: self.refresh_rows())
        sort = tk.OptionMenu(tools, self._sort, "Label", "Username", command=lambda _value: self.refresh_rows())
        sort.configure(bg=PANEL, fg=MUTED, activebackground=PANEL, relief="flat", highlightthickness=0)
        sort.pack(side="left", padx=(8, 0))

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
        self._render_panel()
        self._set_status(f"{len(self.entries)} entries")

    def refresh_rows(self) -> None:
        if self._list_inner is None:
            return
        for child in self._list_inner.winfo_children():
            child.destroy()
        self._render_tags()
        assert self._filter is not None and self._sort is not None
        visible = sort_entries(
            filter_entries(self.entries, self._filter.get(), self._tag),
            self._sort.get(),
        )
        if self.selected_id not in {entry.id for entry in visible}:
            self.selected_id = visible[0].id if visible else None
            self.revealed_id = None
        if not visible:
            tk.Label(self._list_inner, text="No matching entries", bg=PANEL, fg=MUTED).pack(
                anchor="w", padx=12, pady=12
            )
        for entry in visible:
            self._render_row(entry)
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
        if entry_id != self.revealed_id:
            self.revealed_id = None
        self.selected_id = entry_id
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

    def _field(self, parent: tk.Frame, caption: str, value: str) -> tk.Label:
        tk.Label(parent, text=caption.upper(), bg=PANEL, fg=MUTED).pack(anchor="w", pady=(8, 0))
        label = tk.Label(parent, text=value, bg=PANEL, fg=TEXT, wraplength=270, justify="left")
        label.pack(anchor="w")
        return label

    def copy_entry(self, entry_id: str) -> None:
        entry = next((item for item in self.entries if item.id == entry_id), None)
        if entry is None or self.vault_key is None:
            return
        copy_to_clipboard(entry.password)
        self._set_status(f"Copied {entry.label}")

    def view_entry(self, entry_id: str) -> None:
        if self.credential_id is None or self.prf_salt is None:
            self._set_status("View needs Windows Hello, and this window has no passkey yet.")
            return
        if self.revealed_id == entry_id:
            self.revealed_id = None
            self._render_panel()
            self._set_status("Secret hidden")
            return
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
            return
        except (HelloError, SidecarError, OSError):
            self._set_status("Windows Hello did not show the secret.")
            return
        self.revealed_id = entry_id
        self.selected_id = entry_id
        self._render_panel()
        self._set_status("Secret shown until you leave it, lock Windows, or sleep.")

    def _watch_desktop(self) -> None:
        if self.root is None:
            return
        now = time.monotonic()
        slept = now - self._last_tick > 5
        self._last_tick = now
        locked = False
        if self.revealed_id is not None and not slept:
            try:
                locked = workstation_locked()
            except OSError:
                locked = False
        if self.revealed_id is not None and (slept or locked):
            self.revealed_id = None
            self._render_panel()
            self._set_status("Secret hidden")
        self.root.after(400, self._watch_desktop)


def _button(parent: tk.Misc, text: str, command, primary: bool = False) -> tk.Button:
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
        fg=TEXT,
        activebackground="#2a2a2a",
        activeforeground=TEXT,
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
