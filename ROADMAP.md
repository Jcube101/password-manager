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

### PWM-R001: Reduce master password friction with OS keyring / DPAPI
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

### PWM-R007: Encrypted backup helper
- Command that creates a timestamped copy of the current `vault` file into a user-chosen backup location (or default `~/pwm-backups/`).
- Optional: GPG-sign the backup if `gpg` is available (nice-to-have, not required).

### PWM-R008: Config file for defaults
- Small plaintext `config.toml` or `config.json` next to the vault (or in the same user data dir) for:
  - Default Argon2 parameters (advanced users only — still override per-vault header).
  - Default generator settings (length, symbols).
  - Preferred output format.
- The vault itself must remain self-contained.

---

## Larger / Longer-Term (v2+ ideas, low priority)

- PWM-R100: Migrate storage layer to encrypted SQLite (sqlcipher or a simple whole-file encrypted SQLite) while keeping the same crypto primitives and in-memory `Entry` model.
- PWM-R101: Optional TUI mode using `textual` (still local, same vault format).
- PWM-R102: Minimal read-only web viewer (FastAPI + HTMX or static) that can open the vault file when given the master (again, same crypto).
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

Current as of 2026-06-14 (post full E2E + 28/28 tests passing). v1 core is complete. Most items below remain valid for post-v1 work. See `ELI5.md` for approachable overviews and `LEARNINGS.md` for what was actually built and tested in v1.

---

**v1 Status Note**: The dual `--label`/`-l` + positional support, the full CLI surface, crypto roundtrips under real master changes, atomic writes, and Rich output were all validated in an interactive Windows E2E session plus automated tests. See the E2E transcript in the chat history and the top of `LEARNINGS.md`.
