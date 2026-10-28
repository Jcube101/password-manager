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

### PWM-R110: Signet, a desktop window on this PC (agreed 2026-10-28, not started)

The direction for the next surface. The window is named **Signet**. The CLI command stays `pwm`. Do not start coding until SPEC.md is updated. Mockups from the 2026-10-28 session live in `.superpowers/brainstorm/` (gitignored). The preview server was stopped that night.

**Paused here.** The main window is settled. The next unanswered question is what **Create new** asks the user to fill in. Pick the conversation up there.

**Why.** The v1 CLI works. Day to day it is hard to reach because it lives in a terminal, the master password is typed on every command, and there is no place to look at labels. Conversation on 2026-10-28 settled a second surface. The CLI stays. The vault file stays. The crypto stays Argon2id + AES-256-GCM. This is not a hosted website, not a browser extension, and not the TUI in PWM-R101.

**What was agreed**

- A desktop app: its own icon and window on this computer, same kind of program as Calculator. It reads the same vault file.
- Daily unlock is the Windows Hello PIN. Hello holds a passkey on this machine. The PIN is how the user proves themselves to Hello. The app never learns the PIN. Fingerprint or face can stand in for the PIN when the laptop has them.
- This PC is Windows 11 26H2 (build 26300), past the February 2026 update where Windows Hello can return a WebAuthn PRF / hmac-secret value after that check. That secret unwraps the vault key. A prompt that only asks "are you there?" and then unwraps a DPAPI blob is the weaker design in PWM-R001. It is not the unlock chosen for this window.
- First trust: the user types the master password once and opts in. Windows creates the passkey and asks for the PIN. After that, opening the app is the PIN.
- The master password stays the other way in: a new computer, a Windows reinstall, or Hello / TPM failure. A Drive backup of the vault still opens with the master that was current when that copy was made. The PIN secret stays on this PC and does not travel with the file. The CLI keeps prompting for the master with `getpass`.
- Lock when the laptop sleeps (lid close), when Windows locks, and after the user has been away for a few minutes. Drop the key from memory and hide the list. The process may stay open. Coming back asks for the PIN again. If Windows is set to stay awake with the lid shut, the app still locks on session lock and on idle.
- After the PIN, the window shows every label. Secrets stay hidden.
- A create button. It can generate a new password, or save a secret the user pastes. A personal access token and an API key are the same kind of entry as a password: a hidden string and a label. Username, URL, and notes stay as they are on `Entry` today. One screen for all three. TOTP codes are a different idea and stay in PWM-R002.
- An entry can carry more than one tag. Examples the user gave: `api-key` and `agent` on one entry, `password` and `email` on another. This is already the data model (`tags` is a list) and already works in the CLI with a repeated `--tag`. Filtering on one tag shows every entry that includes it. `pwm list --tag` already does that.
- Filter, sort, and those tags on the list.
- Copy puts the secret on the clipboard and leaves it off the screen. Copy uses the unlock already done. It does not ask for the PIN a second time. The clipboard warning still applies: other programs can read it, and Windows clipboard history (`Win+V`) can keep it.
- View shows the secret only after a second Hello prompt. The button is labeled View.
- The window is named Signet. The CLI command stays `pwm`.
- The color is Ink: near-black surfaces, warm off-white text, one brass accent. Chosen 2026-10-28 over Paper, Tide, and Clay.
- The list is the working surface and takes most of the window. Copy is on every row and does not require the row to be open. Clicking a row opens the entry in a side panel. That panel is there because the project is public-facing and the list-plus-entry view looks finished. The opened entry has its own Copy and a button labeled View. The narrow panel is out. Multiple tags show as chips on the row and again on the opened entry.

**Assumptions (correct these before SPEC)**

- A revealed secret covers itself again after a short time.
- Idle lock is a few minutes. The number is not chosen.
- Edit and delete are not specified for the first version of the window. The CLI still has them.
- Where the Hello-wrapped key is stored (vault header extension or a sidecar next to the vault) is not chosen. Loss of Hello must still leave the master-password path working. Fresh salt and nonce rules do not change.
- PRF has to be tried on this machine before the ticket can be called done. The file encryption does not change. Hello only unwraps a key. No new cipher.

**Open**

- What Create new asks for. Not discussed yet. The button can generate a password or save a pasted token or API key. The form itself is undesigned.
- How long a viewed secret stays visible. The button says View. It still asks for the Hello PIN again. The label does not say PIN.

**Related tickets, and what not to build instead**

- PWM-R001 is the same pain (typing the master every time) and a different mechanism (OS keyring / DPAPI). Do not implement R001 as the desktop unlock.
- PWM-R004 stays the CLI ticket for fuzzy search and folders. This window uses the tags that already exist, plus filter and sort.
- PWM-R101 (terminal UI) and PWM-R102 (local web viewer) are other surfaces. They are not this ticket.
- PWM-R002 is TOTP. The user used "token" to mean a personal access token, which is a secret string in the existing password field.

**Acceptance**

- The same vault file opens in the CLI with the master and in the window with the PIN after enrollment.
- A wrong PIN shows no entries.
- Sleep or Win+L hides the entries until the PIN again.
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
- PWM-R102: Minimal read-only web viewer (FastAPI + HTMX or static) that can open the vault file when given the master (again, same crypto). A hosted site was rejected for R110. This ticket remains a different, local, read-only idea.
- PWM-R103: Multi-vault support (`pwm use personal`, `pwm use work`).
- PWM-R104: Audit log of operations (append-only, still inside the encrypted vault or sidecar).
- PWM-R105: Formal property-based tests for the crypto roundtrips and serialization invariants (Hypothesis).
- PWM-R106: Packaging as a single-file executable (PyInstaller, Nuitka, or `briefcase`) for non-Python users.
- PWM-R107: First-class Windows installer / Scoop / winget manifest.

---

## Notes for Future Agents / Humans
- Before pulling any roadmap item into active work, update this file (remove the item), add it to the active task list / chat, and ensure SPEC.md is extended if the contract changes.
- Always re-evaluate security impact. Many of these (keyring, TOTP, import) increase surface area.
- Keep the "educational first" spirit: each new feature should come with clear explanations in code comments and LEARNINGS.md.

Current as of 2026-10-28, paused for the night. v1 core is complete. PWM-R009 (landing page) and PWM-R007 (`pwm backup`) shipped — see "Recently shipped" below. 35 automated tests passing. PWM-R110 is Signet, an Ink-colored desktop window on the same vault, unlocked with the Windows Hello PIN. Not started. The main window is settled. The next question is the Create new form. The CLI command stays `pwm`.

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
