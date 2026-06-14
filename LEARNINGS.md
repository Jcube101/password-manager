# LEARNINGS.md

Running log of technical decisions, gotchas, implementation details, and fixes.  
**Most recent entries at the top.**  
Date in ISO format. Be specific enough that a future agent (or you in 6 months) can understand the context without reading the full git history.

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
