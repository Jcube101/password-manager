# ROADMAP.md

This document contains **future work only**.  
Nothing listed here is in progress.  
Each item is written as a self-contained ticket with enough context that someone can pick it up cold.  
Order is **rough priority / dependency order**, not a commitment.

The current v1 effort is tracked in the active implementation (see SPEC.md for the contract and the agent's todo list for the immediate build steps). When an item moves from roadmap into active work, it is removed from here and the work is described in chat + LEARNINGS.md.

---

## v1 Completion (Current Focus — Do Not Add Here)

Items required to ship a useful, secure, educational v1 CLI are being executed now and are **not** listed below.

---

## Post-v1 / v1.1+ (Nice-to-Haves)

### PWM-R110: Signet, a desktop window on this PC (agreed 2026-10-28, built)

The direction for the next surface. The window is named **Signet**. The CLI command stays `pwm`. The contract is SPEC.md §13. The sidecar and the tkinter window are in the tree. Mockups from that session live in `.superpowers/brainstorm/` (gitignored).

**Built.** The sidecar and a tkinter window are written. The window lists entries, copies a secret, and opens a side panel. Create, Edit, and Delete save with the vault key already in memory: the salt stays and the nonce is fresh. A Hello unlock lasts 24 wall-clock hours. The Start menu Programs folder and the desktop each have a shortcut named Signet. `python -m pwm.shortcut` writes them. They run `pythonw.exe -m pwm.signet`. Typing `pwm` stays the command-line tool.

**Why.** The v1 CLI works. Day to day it is hard to reach because it lives in a terminal, the master password is typed on every command, and there is no place to look at labels. Conversation on 2026-10-28 settled a second surface. The CLI stays. The vault file stays. The crypto stays Argon2id + AES-256-GCM. This is not a hosted website, not a browser extension, and not the TUI in PWM-R101.

**What was agreed**

- A desktop app: its own icon and window on this computer, same kind of program as Calculator. It reads the same vault file.
- Daily unlock is the Windows Hello PIN. Hello holds a passkey on this machine. The PIN is how the user proves themselves to Hello. The app never learns the PIN. Fingerprint or face can stand in for the PIN when the laptop has them.
- This PC is Windows 11 26H2 (build 26300), past the February 2026 update where Windows Hello can return a WebAuthn PRF / hmac-secret value. That secret unwraps the vault key. Tried on this PC on 2026-10-28: API version 9, a 32-byte output, the same salt matched across create and get, a second salt differed, and the temporary passkey was deleted. A prompt that only asks "are you there?" and then unwraps a DPAPI blob is the weaker design in PWM-R001. It is not the unlock chosen for this window.
- First trust: the user types the master password once and opts in. Windows creates the passkey and asks for the PIN. After that, opening the app is the PIN.
- The master password stays the other way in: a new computer, a Windows reinstall, or Hello / TPM failure. A Drive backup of the vault still opens with the master that was current when that copy was made. The PIN secret stays on this PC and does not travel with the file. The CLI keeps prompting for the master with `getpass`.
- A Hello unlock lasts 24 hours. The clock starts at unlock and is not reset by clicks. Sleep, lid close, and the Windows lock do not end it. Windows may still ask for the laptop PIN to reach the desktop. Signet does not ask again during those 24 hours. Quitting Signet locks it early. Changed from 5 minutes on 2026-10-28 because typing the laptop PIN that often defeated the point of the window. A revealed secret still hides on sleep and on the Windows lock. The list comes back without Hello.
- After the PIN, the window shows every label. Secrets stay hidden.
- Create new lives in the side panel. The list stays. The form is one screen for a password, a token, or an API key. Fields: label, username, secret, URL, notes, and tags. Generate fills the secret, or the user pastes one they already have. The secret stays visible while the form is open. After save it hides like every other entry. Generate uses the same default as `pwm generate` (20 characters, symbols on) unless a length control is added later. TOTP codes stay in PWM-R002.
- An entry can carry more than one tag. Examples the user gave: `api-key` and `agent` on one entry, `password` and `email` on another. This is already the data model (`tags` is a list) and already works in the CLI with a repeated `--tag`. Filtering on one tag shows every entry that includes it. `pwm list --tag` already does that.
- Filter, sort, and those tags on the list.
- Copy puts the secret on the clipboard and leaves it off the screen. Copy uses the unlock already done. It does not ask for the PIN a second time. The clipboard warning still applies: other programs can read it, and Windows clipboard history (`Win+V`) can keep it.
- View shows the secret only after a second Hello prompt. The button is labeled View. It stays visible until the user leaves that entry, the PC sleeps, or Windows locks. Leaving means another row, closing the panel, or pressing View again. There is no countdown. Covering the secret does not end the 24-hour unlock. The list never shows it.
- The window is named Signet. The CLI command stays `pwm`.
- The color is Ink: near-black surfaces, warm off-white text, one brass accent. Chosen 2026-10-28 over Paper, Tide, and Clay.
- The list is the working surface. Copy is on every row and does not open the entry. Clicking a name opens the side panel. A Details control at the top pins that panel open. The opened entry has its own Copy, View, Edit, and Delete. The narrow panel is out. Multiple tags show as chips on the row and again on the opened entry. The list has a scrollbar.
- Edit uses the same fields as Create. Save rewrites the vault. Delete asks the user to confirm the label, then removes the entry and rewrites the vault. Neither asks for the PIN again. The window is already unlocked. Edit does not reveal the secret. View still does, under the rule above.

**Written into SPEC.md §13**

- The Hello-wrapped vault key lives in a sidecar file next to the vault, not in the vault header. The CLI keeps reading the vault exactly as it does now. If the sidecar is missing or Hello fails, Signet asks for the master password. The sidecar stays on this PC. Copying it to Drive does not unlock the vault on another computer, because the PRF secret stays inside Windows Hello. Fresh salt and nonce rules do not change.
- PRF was tried on this machine on 2026-10-28. Hello returned a stable 32-byte output, so that output can be the AES-GCM wrapping key directly. The file encryption does not change. Hello only unwraps a key. No new cipher.

**Open**

- Nothing the user still has to choose. The on-machine PRF check passed. The sidecar format is implemented. A tkinter window shows the list, Copy, the side panel, Create, Edit, and Delete. A Hello unlock lasts 24 wall-clock hours. The Start menu and desktop shortcuts exist. Recreate them with `python -m pwm.shortcut` if the virtual environment moves.

**Related tickets, and what not to build instead**

- PWM-R001 is the same pain (typing the master every time) and a different mechanism (OS keyring / DPAPI). Do not implement R001 as the desktop unlock.
- PWM-R004 stays the CLI ticket for fuzzy search and folders. This window uses the tags that already exist, plus filter and sort.
- PWM-R101 (terminal UI) and PWM-R102 (local web viewer) are other surfaces. They are not this ticket.
- PWM-R111 is a later phone client for this same vault. Do not make the vault openable only by this laptop's Hello. The master password must keep opening the file anywhere.
- PWM-R002 is TOTP. The user used "token" to mean a personal access token, which is a secret string in the existing password field.

**Acceptance**

- The same vault file opens in the CLI with the master and in the window with the PIN after enrollment.
- A wrong PIN shows no entries.
- Sleep or Win+L covers a revealed secret. The 24-hour unlock stays. See SPEC.md §13.3.
- Copy does not print the secret. View prints it only after a second Hello prompt.
- A pasted API key round-trips through `pwm get` and `pwm copy` with the master.

### PWM-R001: Reduce master password friction with OS keyring / DPAPI
- Superseded for the desktop window by PWM-R110. That ticket uses Windows Hello PRF, not a DPAPI-wrapped key. Leave this ticket for a possible CLI-only keyring later. Do not build it as the app unlock.
- Context: Typing a long master password on every `pwm add` / `pwm copy` is the biggest real-world usability complaint for local CLI managers.
- Scope: After successful unlock, optionally store the *derived key* (or a session token) in the platform keyring (Windows DPAPI / Credential Manager via `keyring` library or direct `ctypes`/`win32crypt`, macOS Keychain, Linux Secret Service).
- Constraints:
  - Must still support pure file-based master password as fallback (for air-gapped machines, CI, etc.).
  - The vault file itself must remain usable if the keyring entry disappears.
  - Document the new attack surface (someone with the user's OS login can now unlock without the master).
- Acceptance: `pwm config keyring --enable` (or similar) + transparent unlock when possible. Clear UX and security warning on first use.
- Why not in v1: Increases complexity, platform-specific code, and the educational focus was on the core Argon2 + AES-GCM + atomic vault story.

### PWM-R002: TOTP / 2FA code support
- Context: Many people store TOTP seeds alongside passwords today.
- Scope: Add optional `totp_secret` (or `totp_uri`) field to Entry. `pwm totp <label>` that prints the current 6-digit code (and optionally copies it). Use `pyotp` or pure stdlib HMAC+time implementation (the latter preferred for fewer deps in the spirit of v1).
- Constraints: The TOTP secret is just another secret string — it lives inside the same encrypted vault. No special handling beyond that.
- Nice extras: `--time` or live updating display for 30s window.
- Why deferred: Pure password manager utility is already valuable; TOTP is a common follow-up feature request.

### PWM-R003: Passphrase generator (xkcd / diceware style)
- Context: Some users prefer memorable passphrases over high-entropy random strings for certain accounts.
- Scope: `pwm generate --passphrase --words 6 --separator "-"` (or similar). Ship a small embedded wordlist or allow user-supplied list. Still use `secrets` for selection.
- Constraints: Keep the existing char-based generator as default and primary.
- Why deferred: Increases scope (wordlist maintenance, locale considerations). Char generator covers 95% of v1 needs.

### PWM-R004: Richer search & organization
- The desktop window in PWM-R110 already includes filter, sort, and the tags that exist today. This ticket stays the CLI follow-up (fuzzy search, folders). Do not block R110 on it.
- Context: As the vault grows, simple substring search becomes limiting.
- Possible tickets:
  - PWM-R004a: Fuzzy search (rapidfuzz or simple difflib).
  - PWM-R004b: Tag-based filtering + `pwm tags` listing.
  - PWM-R004c: Folders / categories as a first-class prefix on labels (e.g. `work/gmail`).
- Keep the data model backward compatible (the JSON inside the vault is versioned).

### PWM-R005: Import / Export
- `pwm export --format json` (decrypted — with huge warning and confirmation).
- `pwm import --file dump.json` (creates entries, skips or merges on label conflict).
- Also consider CSV and Bitwarden/1Password JSON exports as stretch.
- Must never write decrypted data to disk without explicit user action and warning.

### PWM-R006: Vault statistics & health
- `pwm stats`: count of entries, duplicate passwords (warning only), password age (last updated), weak generator defaults used historically, etc.
- Can be implemented purely after decrypt; no crypto changes.

### PWM-R008: Config file for defaults
- Small plaintext `config.toml` or `config.json` next to the vault (or in the same user data dir) for:
  - Default Argon2 parameters (advanced users only — still override per-vault header).
  - Default generator settings (length, symbols).
  - Preferred output format.
- The vault itself must remain self-contained.

---

## Larger / Longer-Term (v2+ ideas, low priority)

- PWM-R100: Migrate storage layer to encrypted SQLite (sqlcipher or a simple whole-file encrypted SQLite) while keeping the same crypto primitives and in-memory `Entry` model.
- PWM-R101: Optional TUI mode using `textual` (still local, same vault format). Not the answer to the 2026-10-28 UX rework. That is PWM-R110, a desktop window.
- PWM-R102: Minimal read-only web viewer (FastAPI + HTMX or static) that can open the vault file when given the master (again, same crypto). A hosted site was rejected for R110. This ticket remains a different, local, read-only idea. A phone client is PWM-R111, not this ticket.
- PWM-R103: Multi-vault support (`pwm use personal`, `pwm use work`).
- PWM-R104: Audit log of operations (append-only, still inside the encrypted vault or sidecar).
- PWM-R105: Formal property-based tests for the crypto roundtrips and serialization invariants (Hypothesis).
- PWM-R106: Packaging as a single-file executable (PyInstaller, Nuitka, or `briefcase`) for non-Python users.
- PWM-R107: First-class Windows installer / Scoop / winget manifest.
- PWM-R111: Phone access to the same vault, later. Not part of Signet. Do not start it while PWM-R110 is unbuilt.

### PWM-R111: Phone client for the same vault (later, not started)

The user wants to open this vault from their phone someday. The phone has a fingerprint. The laptop does not. This ticket is a direction constraint on Signet, not work to start now.

**What must stay true while Signet is built**

- The PWM1 file plus the master password opens the vault on any device. Hello on the laptop is a local convenience. A phone enrolls its own unlock later, after the master is typed on the phone once. The `.signet` sidecar does not travel.

**How the user expects to host it**

- Not an open website. A progressive web app, or the same idea, served from their Raspberry Pi on a subdomain they control. Cloudflare Access (zero trust) in front, as they already do for other projects. The phone reaches the Pi. The Pi is not the place the secrets are decrypted.

**The packet rule**

- TLS, Cloudflare, and zero trust decide who can connect and they encrypt the connection. They are not the vault encryption. Anything that crosses the network, including what the Pi stores and what Cloudflare can see if it terminates TLS, must be the PWM1 ciphertext (or an equally encrypted blob). A captured packet must not contain the master password, entry plaintext, or the unwrapped vault key. The phone decrypts locally, after the file has arrived, with the master or with a fingerprint wrap that was created on that phone.

**The limit of that rule**

- Ciphertext on the wire does not protect a master password typed into a page the Pi just served. If the Pi or Cloudflare is compromised, it can serve different JavaScript that sends the master elsewhere the next time it is typed. The ticket has to treat the app bundle as trusted code, not only the packets as opaque. How that trust is pinned is undecided. Do not solve it by decrypting on the Pi.

**Out of scope until Signet exists**

- Sync design, the phone UI, Argon2 in the browser, and fingerprint enrollment. No SPEC change for this ticket yet.

---

## Notes for Future Agents / Humans
- Before pulling any roadmap item into active work, update this file (remove the item), add it to the active task list / chat, and ensure SPEC.md is extended if the contract changes.
- Always re-evaluate security impact. Many of these (keyring, TOTP, import) increase surface area.
- Keep the "educational first" spirit: each new feature should come with clear explanations in code comments and LEARNINGS.md.

Current as of 2026-10-28. v1 core is complete. PWM-R009 (landing page) and PWM-R007 (`pwm backup`) shipped — see "Recently shipped" below. 67 automated tests passing. PWM-R110 is Signet, and the agreed window is built. The contract is SPEC.md §13. The sidecar format is implemented. A tkinter window shows the list and Copy. The side panel opens from a name, or stays open when Details is pinned. The list scrolls. Create, Edit, and Delete are in the panel. A Hello unlock lasts 24 wall-clock hours. The Start menu Programs folder and the desktop each have a shortcut named Signet, created by `python -m pwm.shortcut`. They run `pythonw.exe -m pwm.signet`. The taskbar and those shortcuts use a Signet seal, not the Python logo. Windows Hello is owned by Signet's top-level window, so the PIN dialog opens in front of it. The Hello PRF check passed on this PC on 2026-10-28. The CLI command stays `pwm`. Daily unlock is the existing Windows Hello PIN. `python -m pwm.signet` opens the window from a terminal. PWM-R111 records a later phone client on the user's Pi. The network carries ciphertext only. It is not started.

---

**v1 Status Note**: The dual `--label`/`-l` + positional support, the full CLI surface, crypto roundtrips under real master changes, atomic writes, and Rich output were all validated in an interactive Windows E2E session plus automated tests. See the E2E transcript in the chat history and the top of `LEARNINGS.md`.

---

## Recently shipped

### PWM-R009: Bare-`pwm` landing page (shipped 2026-08-16)
- Ticket lived in Post-v1 above, then moved here after implementation (SPEC §7.0).
- `pwm` with no subcommand prints a header-only landing page: path, format, Argon2 params, backup reminder, four daily commands.
- No master prompt, no decrypt, no labels, no entry count. Not a TUI (PWM-R101 still deferred).
- Details and the CliRunner-vs-module-level-Console gotcha: `LEARNINGS.md`.

### PWM-R007: Encrypted backup helper (shipped 2026-08-16)
- `pwm backup` / `pwm backup --dest DIR`. No master, no decrypt — copies the ciphertext to `pwm-vault-YYYY-MM-DD-HHMMSS`.
- Dest: `--dest`, else `PWM_BACKUP_DIR`, else `~/pwm-backups`. GPG signing still not done (was a stretch).
- Built after the user asked "is there a simple command like pwm backup?" while standing up a new vault.
