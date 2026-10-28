# LEARNINGS.md

Running log of technical decisions, gotchas, implementation details, and fixes.  
**Most recent entries at the top.**  
Date in ISO format. Be specific enough that a future agent (or you in 6 months) can understand the context without reading the full git history.

---

## 2026-10-28 — A later phone client must see ciphertext only (PWM-R111)

The user may want the vault on their phone later. It would be a progressive web app served from their Raspberry Pi, behind Cloudflare Access, on a subdomain they already know how to protect. That is not Signet, and it is not a reason to change the vault format.

TLS and zero trust are the front door. They are not the vault encryption. Packets, the Pi's disk, and anything Cloudflare can see at the TLS boundary must be PWM1 ciphertext. The master, entry plaintext, and the unwrapped key stay off that path. The phone decrypts locally. A stolen packet is then still an encrypted vault.

That rule does not cover a compromised app bundle. If the Pi serves the page, a compromised Pi can serve JavaScript that exfiltrates the master the next time it is typed. Recorded so a future build does not treat Cloudflare as a substitute for decrypting on the phone. No SPEC change. No code.

---

## 2026-10-28 — User accepted the 24-hour unlock and the click-to-start

The user said the PIN-change behavior, the 24-hour Hello unlock, and launching Signet from a shortcut (not from `pwm`) look good. SPEC.md §13 is the contract they accepted. No Signet code yet.

---

## 2026-10-28 — 24-hour Signet unlock, and a PIN change needs nothing from the user

The user does not want Hello every 5 minutes. SPEC §13.3 now says one Hello unlock lasts 24 hours, starting at that unlock, not extended by clicks. Sleep and the Windows lock do not end it. Windows itself may still ask for the laptop PIN on wake. Signet must not ask a second time inside those 24 hours. Quitting Signet locks it early. A secret shown with View still hides on sleep and on the Windows lock. The list comes back without Hello.

A Windows PIN change does not notify Signet and does not need a step inside Signet. Signet never stored the digits. Windows asks for the new PIN at the next Hello prompt and still returns the same PRF output, as long as the passkey was not removed. Removing the PIN or clearing the TPM is the case that falls back to the master password.

Launch, once built: Start menu and a desktop shortcut named Signet. Typing `pwm` stays the CLI and does not open the window. The program is not installed yet.

---

## 2026-10-28 — Signet is SPEC §13. The PIN is the laptop PIN

The user confirmed Signet uses the Windows Hello PIN they already use to sign in. It is not a new PIN and it is not a 4-digit vault PIN. A normal Windows PIN change (old PIN known, new PIN set) keeps the passkey. Removing the PIN or clearing the TPM can destroy it. The master password is the recovery path. A 4-digit app PIN was refused because 10,000 guesses is too weak for a file that can be copied.

Written into SPEC.md §13. Still no Signet code.

Signet saves are an exception to "fresh salt on every save." The window holds the unwrapped vault key, not the master, and the master must never be written into the sidecar. A Signet save uses a fresh nonce and the existing salt. CLI saves still rotate the salt and then the sidecar no longer matches until the user types the master once. AES-GCM key reuse is safe only with a unique nonce. Do not "fix" Signet saves by rotating the salt unless the master is in memory for that operation.

---

## 2026-10-28 — Signet locks after 5 idle minutes

The user agreed. Five minutes with no click or keypress in the Signet window locks it. Time spent in another app counts. Sleep and the Windows lock still lock it immediately. The key leaves memory and the list hides. Coming back is the Hello PIN. Recorded on PWM-R110. Still not in SPEC. No code.

The Hello-wrapped vault key will live in a sidecar next to the vault, not in the header, so the CLI file format stays as it is. That storage choice is for the spec. It was not a separate question to the user.

---

## 2026-10-28 — Edit and Delete panels accepted

The user looked at the open-entry buttons (Copy, View, Edit, and a quieter Delete) and the delete confirm that requires the label, and said they look good. Recorded on PWM-R110. Still not in SPEC. No code.

---

## 2026-10-28 — Edit and Delete on the open entry

The user wants both on the Signet side panel. Edit uses the same fields as Create and does not reveal the secret. Delete asks for the label to be confirmed, then removes the entry. Neither asks for the Hello PIN again, because the window is already unlocked. Save and delete both rewrite the vault the way the CLI does. Recorded on PWM-R110. Still not in SPEC. No code.

---

## 2026-10-28 — View stays until you leave

After the second Hello PIN, the secret stays on the open entry until the user leaves it or the window locks. Leaving means another row, closing the panel, or pressing View again. Sleep, Windows lock, and idle lock cover it too. No countdown. The list never shows it. The user agreed. Recorded on PWM-R110. Still not in SPEC. No code.

---

## 2026-10-28 — Create form accepted

The user looked at the full side-panel form (label, username, secret, URL, notes, tags, Generate or paste, visible until save) and said it looks good. No length control. Recorded on PWM-R110. Still not in SPEC. No code.

---

## 2026-10-28 — Create new lives in the side panel

The user chose option A. Create new does not cover the list and does not start with a "password or token?" step. The list stays, and the side panel becomes a blank entry. One form for a password, a personal access token, or an API key. Fields on that form: label, username, secret, URL, notes, tags. Generate fills the secret, or the user pastes one. The secret is visible while creating and hides after save. Generate follows `pwm generate` defaults (20 characters, symbols on). Still not in SPEC. No code.

---

## 2026-10-28 — Signet, in Ink

The desktop window's display name is Signet. The CLI command stays `pwm`. Do not rename the console script. Color is Ink: near-black surfaces, warm off-white text, a single brass accent. Chosen over Paper, Tide, and Clay, and over the names Coffer, Latch, and Folio. Recorded on PWM-R110. Still not in SPEC. No code.

---

## 2026-10-28 — Desktop window layout: list works, side panel is the look

Follow-up to PWM-R110. The user wants the full list as the functional surface. Copy stays on every row and does not require opening the entry. Clicking a row opens a side panel with the rest of the entry (username, URL, notes, tags, hidden secret). The panel has Copy and a button labeled View. View still requires a second Hello PIN. The label does not say PIN. The panel is intentional even though copy does not need it: this is a public-facing project and the list-plus-entry view looks finished. Several tags per entry, already the data model. Narrow panel is out. Still not in SPEC. No code.

---

## 2026-10-28 — Desktop window is the next surface (PWM-R110), not built

The user wants to rethink daily use. The CLI stays. The pain is reaching a terminal, typing the master on every command, and having no list of labels to look at.

Agreed in conversation, recorded in `ROADMAP.md` as PWM-R110. Not in SPEC. No code.

- A desktop window on this PC, same vault file.
- Daily unlock is Windows Hello PIN via a passkey whose PRF secret unwraps the vault key. This PC is Windows 11 26H2 build 26300, which is past the February 2026 Hello hmac-secret update. Still has to be proven on the machine.
- Master password remains recovery (new PC, reinstall, Hello failure) and remains what the CLI asks for. The PIN secret does not travel with the Drive backup.
- Lock on sleep, Windows lock, and idle. Wipe the key. Coming back is the PIN again.
- The list shows labels. Copy uses the unlock already done and does not show the secret. View asks for the PIN again.
- Personal access tokens and API keys are the same entry as a password. A tag can say `token` or `api-key`. TOTP stays PWM-R002.
- PWM-R001 (DPAPI / keyring) is the weaker unlock and is not the app design. PWM-R101 and PWM-R102 are other surfaces.

Layout (narrow panel, full list, or list plus detail) was still open when this was written.

---

## 2026-08-16 — Local vs cloud: having a backup *folder* is not a backup

After `pwm backup` shipped, the user asked whether they had a local copy, a cloud copy, or both. We listed the actual files instead of assuming.

| Path | Size | Meaning |
|---|---|---|
| `%LOCALAPPDATA%\pwm\pwm\vault` | 120 B, 2026-08-16 | Live **new** vault. Only copy. |
| `%LOCALAPPDATA%\pwm\pwm\vault.unreadable-2026-08-16` | 596 B, 2026-06-15 | Parked old vault. Same disk as live. Not a backup. |
| `G:\My Drive\Miscellaneous\Password Manager\Backups\pwm-vault-2026-08-16` | 596 B, 2026-06-15 | Cloud copy of the **old** vault. Brick (forgotten master). |
| `~/pwm-backups` | missing | `pwm backup` has not been run without `--dest`. |
| `PWM_BACKUP_DIR` | unset | Profile not wired yet. |

Lesson: a dedicated Drive folder plus an old dated file feels like "I have cloud backup." They did not. The new vault had never been copied. README now says how to tell (size + date of `pwm-vault-*` vs the live file) and that parked AppData files are not a second copy.

No code change.

---

## 2026-08-16 — PWM-R007: `pwm backup`

User created a new vault after losing the master and asked: "how do I back it up? Is there a simple command like pwm backup?" There was not. Copy-Item plus a long Drive path is not a daily habit.

Pulled PWM-R007. SPEC §7.11. Implementation:

- `Vault.backup(dest_dir)` copies bytes with `shutil.copy2` + sibling `.tmp` + `os.replace`. No unlock.
- Name `pwm-vault-YYYY-MM-DD-HHMMSS` (and `-1` if that second already exists).
- Dest order: `--dest` → `PWM_BACKUP_DIR` → `~/pwm-backups`.
- CLI reminds that the copy still needs the master. Warns if they hit the same-machine default with no env var / no `--dest`.
- Did **not** GPG-sign (roadmap stretch). Did **not** hard-code the user's `G:\My Drive\...` path into the tool — that belongs in the profile as `PWM_BACKUP_DIR`.

Teaching point: a backup of an encrypted vault is just a file copy. The interesting part is making the destination sticky and never decrypting "to be helpful."

35 tests.

---

## 2026-08-16 — Real user forgot the master password

Not a hypothetical. After getting daily use working (profile wrapper, landing page, Drive backups), the user could not recall the master and chose to start over. They asked to log it as a lesson. They are not stupid; this is the primary real-world failure mode of a local-only vault with no recovery.

**What the design did (correctly)**
- Master is never stored. Drive copies of `vault` are the same lock. `change-master` needs the old master. There is no reset path. The file without the phrase is a brick. That is the security model, not a bug.
- Live vault at `%LOCALAPPDATA%\pwm\pwm\vault` (596 bytes, last write 2026-06-15) was **renamed**, not deleted: `vault.unreadable-2026-08-16`. Slim chance if the phrase comes back. Google Drive dated copies of that same ciphertext stay as they are.

**What the product got wrong in the messaging**
- We nagged hard about **backing up the file** ("it is the only copy of your data") and barely about **remembering or writing down the master**. Those are two different bricks. The user did the file part (G: folder, Copy-Item, the whole conversation) and still lost access.
- `pwm init` only said to back up the file. That is incomplete. A file backup without the master is a decorated paperweight.

**What we will not do**
- Add a reset / recovery code / email / security questions. That is a second way in.
- Delete the old file "to be tidy."
- Put the master in a Google Doc next to `G:\My Drive\Miscellaneous\Password Manager\Backups`.

**What we will do**
- Tell the truth in README: forgot master → move the file aside → `pwm init`. Reset site passwords out-of-band.
- Strengthen the `init` success line: back up the file **and** write the master on paper in a physical place.
- For a *new* master: a sentence they can actually type, written down *before* `pwm init`, then stored on paper (drawer / safe), not in the cloud folder.

**Related roadmap, not a fix for this incident**
- PWM-R001 (OS keyring) is the only feature that would have helped "I forgot, but I unlocked last week." It also means anyone on the unlocked Windows account can open the vault. That trade-off is now less abstract.

No crypto change.

---

## 2026-08-16 — Google Drive as G: for backups

User asked whether backing up to Google Drive (mapped as `G:`) is a problem because it is connected to the cloud.

Answer we documented: **copies yes, live vault no.**

- The vault is already Argon2id + AES-GCM. Uploading a dated copy to `G:\pwm-backups\` gives Google the ciphertext, not the plaintext. That is the same class of trade-off as any cloud-hosted password manager, except this prototype has not had a security review and the master is the entire remaining secret.
- Pointing `--vault-path` at `G:` for daily use is a different, worse idea: Drive can snapshot mid-write, invent conflict copies, lock files, and upload every mutation.
- Date-stamped filenames avoid Drive's "conflicted copy" mess. Folder must not be shared. Master must not live in a Doc beside it. Stream/online-only files need to finish downloading before a restore is trustworthy.
- A USB copy is still the cleaner offline spare; Drive is a convenient second copy.

No code change. README "How to back up" now has an explicit `G:` subsection and the table no longer lumps all cloud into one vague "trade-off" cell.

---

## 2026-08-16 — "Back up this file" needed actual steps

The landing page (and `init`) tell the user to back up the vault, but neither the command nor the README showed a copy-paste way to do it. User asked "How do I do that?" after seeing the line.

Added a README section "How to back up": `Copy-Item` of the header-only path, what *not* to copy (`vault.tmp`, git), destination trade-offs (same disk / USB / cloud), restore via overwrite or `--vault-path`, and the change-master vs old-backup rule.

Did **not** implement `pwm backup` (PWM-R007). The user asked how, not for a new command. The whole-file story is simple enough that a helper would mostly date-stamp a copy — still valid later, not required to answer the question.

---

## 2026-08-16 — PWM-R009: bare-`pwm` landing page

User asked whether pwm should have a "home screen." We agreed: no stay-open TUI (that remains PWM-R101), but yes a header-only landing page when `pwm` is invoked with no subcommand.

Ticket written into ROADMAP first (PWM-R009), then SPEC §7.0, then implemented and pulled out of future work.

**What it does**
- No master prompt. No decrypt. No labels. No entry count.
- No vault → first-run panel pointing at `pwm init` and the configured path.
- Vault exists → path, format, Argon2 params, backup reminder, four daily commands.
- Salt/nonce/ciphertext length stay on `pwm info`. `--help` / `--version` unchanged.

**Implementation notes**
- Hooked in the existing `@app.callback(invoke_without_command=True)` when `ctx.invoked_subcommand is None`.
- Reuses `Vault.inspect_header()`. Missing-vault result now also includes `path` so callers do not have to special-case it.
- First draft used the module-level `Console()` to print a `Panel`. CliRunner captured a single ellipsized line (no newlines, path gone). Switched to `rprint(Panel(...))` so output binds to the current stdout — same pattern as the rest of the CLI. Teaching point: a process-global Rich `Console` created at import time does not see Typer's redirected stdout.

**Tests**: 3 new CliRunner cases (no vault, existing vault, `--help` still the command list). Suite is 31.

No crypto change. No data-model change.

---

## 2026-08-16 — Windows launcher breaks after the repo is moved

User added the README profile wrapper (`pwm.exe`) and got:

```
Fatal error in launcher: Unable to create process using
'"C:\Users\jobjo\projects\password-manager\.venv\Scripts\python.exe"
"C:\Users\jobjo\Github\password-manager\.venv\Scripts\pwm.exe"'
```

Root cause: this repo used to live at `C:\Users\jobjo\projects\password-manager` and was moved to `Github\password-manager` with the `.venv` copied along. Two things were still baked to the old path:

1. **`pwm.exe`** (setuptools/distlib Windows console-script stub) embeds the absolute path to `python.exe` at `pip install` time. It is not a real relocatable binary.
2. **`__editable__.pwm-0.1.0.pth`** pointed at `C:\Users\jobjo\projects\password-manager\src`. So even `python -m pwm` failed with `No module named pwm`. `pip show pwm` reported `Editable project location: C:\Users\jobjo\projects\password-manager`. `pyvenv.cfg` still recorded `command = ... -m venv C:\Users\jobjo\projects\password-manager\.venv`.

The interpreter itself (`Github\...\python.exe`) ran fine. Only the stubs and the editable map were stale.

Fix applied: re-ran `python.exe -m pip install -e ".[dev]"` against the *current* interpreter. That rewrote the launcher and the `.pth` to `C:\Users\jobjo\Github\password-manager`. Both `pwm.exe --help` and `python -m pwm --help` then worked.

Docs change: README now recommends the profile wrapper call `python.exe -m pwm`, not `pwm.exe`, and explains that a moved venv should be recreated (or at least reinstalled) rather than copied.

Teaching point: Windows venvs are not portable. Console-script `.exe` files and editable `.pth` files are absolute-path snapshots.

---

## 2026-08-16 — Day-to-day usage documented in README

User asked how to actually *live* with `pwm` after v1 shipped. README was still install-first ("once v1 is complete") with a stale clone path (`projects\password-manager`) and a guessed vault location (`%APPDATA%\pwm\vault`).

What we added / fixed (docs only, no code):

- Practical daily-use guide: mental model (unlock → one job → process exits), PowerShell profile wrapper so `pwm` works from any directory without activating the venv, cheat sheet, a "typical week" walkthrough, habits, explicit non-goals, multi-vault via `--vault-path`.
- Vault location is now "run `pwm info`" instead of hardcoding a path. `platformdirs.user_data_dir("pwm")` on Windows defaults to Local (not Roaming) and, because `appauthor` is omitted, often nests as `...\pwm\pwm\vault`. Guessing `%APPDATA%\pwm\vault` was wrong; `info` is the contract with the user.
- Documented the two real daily-use friction points honestly:
  1. Master is typed on every vault command (by design; no session/keyring in v1).
  2. `pwm edit --password` puts the new secret in shell history. `add` can hide/generate; `edit` cannot yet. Called out as a v1 UX gap rather than silently changing SPEC.
- Also called out clipboard history (`Win+V`) and "don't pass `--password` on `add`".

No SPEC change. If we later add a hidden password prompt on `edit` (or `--generate` on `edit`), that would be a small, user-facing contract extension and should go through SPEC first.

---

## 2026-06-14 — Project Kickoff & Architecture Baseline

- **CLI command name**: `pwm` (user preference stated explicitly).
- **Language for v1**: Python >= 3.10. Rationale:
  - Best match for conservative audited crypto requirements (`cryptography` + `argon2-cffi`).
  - Excellent stdlib for the rest (`secrets`, `getpass`, `pathlib`, `json`, `uuid`, `dataclasses`, `os` for atomic replace).
  - Fast iteration with `typer` + `rich`.
  - Educational value: bytes handling, KDF tuning, cross-platform user data paths, and the limits of Python memory clearing are all valuable to experience directly.
  - Diversifies from the user's heavy TS/JS usage elsewhere.
- **Scope**: Pure CLI (no web UI or TUI in v1). Matches README goals for speed, auditability, and minimal attack surface.
- **Storage**: Single encrypted file (not SQLite/sqlcipher yet). Reasons: simplest to audit (one blob you can hexdump), trivial backup story, no DB schema or migrations to explain in v1. We can evolve to an encrypted container later if query needs arise.
- **Crypto decisions** (strictly following user's conservative rules):
  - Key derivation: **Argon2id only** via `argon2.low_level.hash_secret_raw(..., type=argon2.low_level.Type.ID)`.
  - Encryption: **AES-256-GCM** via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. Provides confidentiality + built-in authentication tag.
  - Never roll our own anything. No custom padding, no hand-rolled CTR, no home-grown KDF.
- **Argon2id parameters (initial)**:
  - `memory_cost=65536` (64 MiB)
  - `time_cost=3`
  - `parallelism=4`
  - `hash_len=32` (for 256-bit key)
  - Rationale: OWASP Password Storage Cheat Sheet gives a *minimum* of 19 MiB / t=2 / p=1 for general use. For a local password *vault* (KDF runs infrequently on a desktop-class machine), higher memory is practical and provides meaningfully better resistance to GPU/ASIC attacks. Target unlock time roughly 1–2.5s on typical hardware. Parameters are stored in the vault header so we can raise them safely in the future.
  - Source references: OWASP cheat sheet (multiple 2025–2026 discussions), RFC 9106 guidance on interactive vs. archival KDF targets, and common practice in modern password managers (Bitwarden experiments, etc.).
- **Vault on-disk format** (see SPEC.md for exact byte layout):
  - Tiny unencrypted header containing magic, format version, the three Argon2 params, 16-byte salt, 12-byte nonce.
  - Remainder = AES-GCM output (ciphertext with 16-byte auth tag appended by the library).
  - Plaintext inside = UTF-8 JSON of a small dict: `{"version": 1, "created_at": "...", "entries": [...]}`.
  - Fresh salt + fresh nonce on **every** re-encryption (every mutation + master change).
- **Entry model**:
  - `id`: UUID4 string (stable internal identifier).
  - `label`: human-friendly, treated as unique for add/get/copy (case-sensitive for now; search is case-insensitive).
  - Optional: `username`, `url`, `notes`, `tags` (list of strings).
  - `password` stored encrypted as part of the whole vault (not per-entry encryption).
  - `created_at` / `updated_at`: ISO-8601 strings (UTC).
- **Atomic writes**: Always write to `vault.tmp` (sibling), then `os.replace`. Prevents partial/corrupt vault on crash or power loss during save. Documented as required in SPEC.md.
- **Master password UX**:
  - Prompt with `getpass.getpass` on every command that needs the vault (simple & safe for v1; no long-lived agent process or keyring caching yet).
  - `pwm init` (or implicit on first `add`) creates the vault.
  - `pwm change-master` must re-derive with old, decrypt, then re-encrypt everything under new master + new salt/nonce.
- **Clipboard**:
  - Use `pyperclip` for cross-platform copy.
  - Known limitations (will be documented in code + README): other processes can read the clipboard, Windows 10+ clipboard history (Win+V) can retain the value, no true "secure clipboard" primitive on most desktops. Best-effort timed clear is possible but racy; for v1 we will note the risk and let the user decide how long to leave the value there.
- **Password generator**:
  - Uses only `secrets` + `string` (or explicit char sets).
  - Customizable via flags: length, enable/disable upper/lower/digits/symbols, custom symbols string, exclude ambiguous characters.
  - Default: strong (20+ chars, all classes).
  - Option to copy directly from generate.
- **Error handling philosophy**:
  - Wrong master or corrupt vault → single clear message: "Decryption failed. Wrong master password or the vault file is corrupted."
  - No stack traces containing secrets.
  - No distinction in error messages that would help an attacker (e.g. "bad tag" vs "wrong key").
- **Dependencies chosen for v1** (runtime):
  - `typer` (modern CLI with excellent help + autocompletion)
  - `rich` (tables, spinners while Argon2 runs, styled output)
  - `cryptography`
  - `argon2-cffi`
  - `pyperclip`
  - `platformdirs` (correct user data dir on Windows/macOS/Linux)
- **Packaging**: `pyproject.toml` + console script entry point so `pwm` command appears after `pip install -e ".[dev]"`. This is good modern practice and teaches packaging.
- **Layout**: `src/pwm/` package layout (clean, supports editable installs correctly).
- **Initial todo structure** recorded in the agent's internal task list and mirrored into ROADMAP.md.

These decisions were discussed at length with the user before any code was written. The user explicitly approved moving forward.

---

## 2026-06-14 — File & Directory Decisions

- Vault file name inside the platformdirs user data dir: `vault` (no extension). Easy to find for backups, still obvious what it is.
- Support `--vault-path` override for development, testing, and power users (bypasses platformdirs).
- `.gitignore` was already excellent (covered `vault*`, Python artifacts, Node artifacts, OS junk). No immediate changes required, but we will keep it updated.
- Project stays in `projects/password-manager` until it proves useful (per original README).

---

## 2026-06-14 — Future Evolution Notes (captured early)

- Post-v1 possible additions (see ROADMAP): OS credential manager / DPAPI integration to reduce master password typing, TOTP field + `pwm totp`, fuzzy search, passphrase (xkcd-style) generator option, export/import with warnings, richer tags/folders.
- If vault grows very large we may consider migrating the storage layer to an encrypted SQLite (sqlcipher or equivalent), but the crypto primitives and in-memory model should remain reusable.
- Memory zeroization is known to be imperfect in CPython. We will do best-effort `del` + `gc.collect()` on derived keys and note the limitation.

---

## 2026-06-14 — Automated test results after E2E

User ran in their active test venv (after re-`pip install -e`):

```
pytest tests/test_cli.py -q
.......                                                           [100%]

pytest -q
............................                                      [100%]
```

- 7 CLI-specific tests (version, generate, help texts including dual --label support, info on non-vault, etc.) all green.
- 28 total tests across crypto + generator + vault + CLI all passing.

This gives strong regression protection for the non-interactive surfaces and the crypto invariants.

## 2026-06-14 — Background task cleanup

During the development session there was a long-running background verification task (the `.venv-dual` one that was spun up to confirm dual-label help text before the user's full E2E). It had been backgrounded because the `pip install -e` + CLI invocations were slow.

- It was no longer needed once we had the user's complete E2E transcript + fresh pytest results.
- The task was terminated and the leftover `.venv-dual` directory + any stray python processes were cleaned up.
- Partial output from it had already confirmed that `pwm get --help` and `pwm copy --help` correctly showed both the `[LABEL]` positional argument and the `--label` / `-l` options.

Future background verification runs should be used more sparingly or with shorter timeouts.

## 2026-06-14 — Real-world E2E test results (user-provided output)

Full interactive end-to-end run on Windows/PowerShell in a fresh venv with --vault-path isolation:

**Successes:**
- --version, --help, generate (with --copy + warning) all work without vault.
- init creates vault correctly, prints backup reminder with the exact path used.
- add --label + --generate + multiple --tag works (prompts master once per command).
- list produces clean Rich table (passwords hidden by default).
- search works case-insensitively.
- get and copy exercised in **both** positional style (`pwm get "Gmail Test"`) and flag style (`pwm get --label "Gmail Test" --show-password`, `pwm copy --label ...`). Both styles function perfectly.
- edit in both styles.
- delete --yes works, "No entries." message appears.
- change-master fully works (prompts current + new x2), vault is re-encrypted, subsequent list requires the *new* master and succeeds.
- All crypto roundtrips (including master change) were exercised successfully in a real session.
- Dual label support for get/copy/delete/edit is now validated in practice.
- Clipboard warnings appear on copy (as intended for education).

**Observations / minor UX items noted during real use:**
- Every data-accessing command re-prompts for the master password (by design for v1 simplicity/safety; no session caching or keyring yet). This was noticeable across ~15 prompts but acceptable for the prototype.
- When running `info` with a --vault-path that didn't exist yet (or variable not expanded in paste), it fell back to printing the platform default. The attempted path wasn't surfaced. **Fixed** (see below).
- Default location message in one run showed `...\pwm\pwm\vault` (likely platformdirs + timing of $var expansion or local config). The improved info message now always shows exactly what path the current invocation is using.
- Attempting the old positional style on `add` (e.g. `pwm add SomeLabel ...`) will now surface Typer's "Missing option '--label'" (or similar). Help text for `add` makes the requirement clear. We left it this way since `add` is the "property-heavy" command.
- No security issues, no crashes, atomic writes + re-encrypt on change-master worked transparently.
- Temp vault in %TEMP% was used cleanly via --vault-path; real user data dir was not polluted.

**Fix applied as a result of this run:**
- Updated `info` command (and slightly the inspect_header path) to report the *actually configured/attempted path* for the current invocation when no vault exists, plus the default for reference. Much clearer when using --vault-path during testing or for multiple vaults.

This E2E gives high confidence that the core (crypto, vault, dual-style CLI) is solid for v1 educational use.

## 2026-06-14 — Dual --label/-l support added for target commands

- Per user request after initial testing ("Yes, that makes sense. Let's do that."), extended get/copy/delete/edit to accept the label either positionally *or* via `--label` / `-l`.
  - Pattern used (standard for Typer when you want both styles):
    - `label: Optional[str] = typer.Argument(None, help="... (positional or use --label/-l)")`
    - `label_opt: Optional[str] = typer.Option(None, "--label", "-l", ...)`
    - `target = label or label_opt`
    - Runtime check + clear error if neither provided.
  - Benefits:
    - `pwm copy Gmail` (short, natural for frequent ops)
    - `pwm copy --label Gmail` or `pwm copy -l Gmail` (explicit flag style, matches add and user expectations from planning)
    - Both styles now documented in each command's `--help`.
  - `add` remains `--label`/`-l` only (as it's the "create" command with many options).
  - `search` query stays positional (it's not an exact label lookup).
- Verified via fresh venv: help text now shows both [LABEL] argument + --label option; bare command gives "A label is required..." message; --label flag parses correctly (fails later on missing vault, as expected).
- This was one of the "open items". Updated internal checklist.

## 2026-06-14 — Bug fixes during initial user testing

- **--version reported "Missing command"**: The `@app.callback()` was missing `invoke_without_command=True`. This is a common Typer gotcha for global eager options like `--version` / `-V` when no subcommand is provided. Fixed by adding the flag; now `pwm --version` cleanly prints `pwm X.Y.Z` and exits.
- **"--lable" (or --label) "no such option" on add**: `add` was using `typer.Argument` for the label (following the "or positional" note in SPEC). This meant users trying the flag style `pwm add --label Gmail ...` (as shown in early planning notes and README sketches) got "No such option". 
  - Changed the `label` param in `add(...)` to a required `typer.Option(..., "--label", "-l", ...)`.
  - Result: `pwm add --label "Gmail" --username ... --generate` now works as expected (and `pwm add -l Gmail`).
  - Other "target" commands (`get`, `copy`, `delete`, `edit`) keep the label as a clean **positional argument** (e.g. `pwm copy Gmail`, `pwm get Netflix`). This is better UX for frequent short commands. Their `--help` makes it obvious.
  - Updated verification confirmed: `pwm add --help` lists `--label` / `-l` as required, and typos produce helpful "No such option: --lable (Possible options: --label)" message.
- These were the exact issues reported in the first round of testing. Code changes are minimal and match the educational goal (clear, discoverable CLI).
- Re-install with `pip install -e .` (or `pip install -e ".[dev]"`) in your test venv to pick up the fixes.
- No changes needed to SPEC (it allowed "positional or --label"); LEARNINGS and actual help text now reflect the final chosen UX.

## 2026-06-14 — Implementation Phase (Crypto, Vault, Generator, CLI)

- All core layers implemented against SPEC.md and verified in one go.
- **Crypto layer (crypto.py)**: Header packing with struct (little-endian), AAD binding for the header prefix (magic+params+salt), fresh os.urandom salt+nonce on every encrypt_vault call, clean VaultDecryptionError wrapper around InvalidTag. get_header_info() helper for safe inspection.
- **Tests for crypto**: 9 tests covering roundtrips, wrong master (generic message), tamper detection, custom params, different nonces/salts on re-encrypt. All passed on first run in verification venv.
- **Generator (generator.py)**: Pure secrets + explicit alphabet building. Default 20 chars, full classes, sensible exclude list. CLI exposes all the controls. Tests validate length, exclusions, and error cases for degenerate alphabets.
- **Models + Vault**: Entry dataclass with touch() and ISO timestamps. Vault handles platformdirs default path, atomic write (tmp + os.replace + fsync), in-memory list after unlock, label uniqueness, search across multiple fields (case-insensitive), full change-master (re-encrypt under new master + new salt/nonce), lock() best-effort gc.
- **Atomic write gotcha handled**: Using sibling .tmp + os.replace is reliable cross-platform (including Windows) when target and tmp are on same volume. fsync before replace for extra durability.
- **CLI (cli.py + clipboard.py)**: Full command surface matching the spec (init, generate with rich options + --copy, add (with internal generate fallback), list/search with hidden pw by default + --show warning, get, copy (with security warning), delete with confirm, change-master, info (header only)).
  - Uses typer for structure + rich Console/Table/status spinners.
  - Master prompts via getpass.getpass only.
  - --vault-path global option wired through ctx.obj for all commands.
  - Clipboard wrapper documents the real risks (other processes, Win+V history) instead of pretending it's "secure".
- **Verification run**: Full pytest (crypto + generator + vault integration) + direct Vault usage flow (create, add, re-unlock, list) + generator all succeeded in an isolated venv on this Windows machine. A second run confirmed the `pwm` console script entrypoint is registered after `pip install -e .` and `pwm generate` produces output.
- **Minor issues encountered & fixed during build**:
  - PowerShell command chaining (&& vs ; and redirection) for automated verification — documented here so future agents know to use full venv python paths or separate steps.
  - In non-tty automated runs, getpass for init/change-master is hard to script (expected); manual user testing is the real verification path for those flows.
  - Version flag + shell echo mixing in test output (cosmetic only).
- **No changes to SPEC required** — the implementation stayed faithful. The header AAD choice and the exact struct layout were implemented exactly as described.
- **Next for user**: Follow the setup in the new README section (or the commands we used in verification). Then do a real interactive end-to-end: `pwm init`, add a few entries, list, copy, change-master, confirm old master no longer works.

All v1 core functionality for the educational password manager is now present and tested at the module level.

---

(End of initial entries. New learnings will be prepended above this line as the build proceeds.)
