# pwm — Local-First Password Manager (CLI)

Quick, auditable, educational password manager that stores everything in a single encrypted file on your machine.

**Status**: v1 complete and tested.

- Full E2E interactive run on Windows (init → add/generate in both label styles → list/search/get/copy/edit/delete → change-master) succeeded.
- All 28 automated tests pass (`pytest -q`).
- CLI tests specifically for non-interactive paths + help text also pass.
- Dual label interface (`pwm copy Gmail` or `pwm copy --label Gmail`) is fully supported and exercised.

See `ELI5.md` for explanations at 5 different levels of complexity (kid → expert).  
See `LEARNINGS.md` for the full build log, decisions, and real-user testing notes.  
See `SPEC.md` for the implementation contract.

The project is intentionally educational first: small, auditable, conservative crypto, explicit limitations.

## Goals for v1

- Store credentials locally in one encrypted vault file
- Strong master password (never stored in any form)
- Conservative, library-only cryptography (Argon2id + AES-GCM)
- Basic operations: generate, add, list, search, get, copy (clipboard), edit, delete, change-master
- Pure CLI (`pwm` command) — fast, scriptable, easy to audit
- No network, no cloud, no browser component
- Excellent learning artifact: every decision documented

## Security Posture (Important)

- We **never** roll our own crypto primitives.
- Key derivation: Argon2id (via `argon2-cffi`).
- Vault encryption: AES-256-GCM (via `cryptography`).
- Fresh random salt + nonce on every re-encryption.
- Atomic file writes (temp + replace) so a crash cannot corrupt your vault.
- The vault file lives in your platform user-data directory and is covered by `.gitignore`.
- Clipboard has inherent risks (documented in `LEARNINGS.md` and in command help).

See `SPEC.md` for the exact on-disk format, data model, and layer contracts.  
See `LEARNINGS.md` for the rationale behind every major decision.  
See `AGENTS.md` if an AI is helping with future changes.  
See `ROADMAP.md` for what is deliberately out of scope right now.
See `ELI5.md` for explainations of the pwm password manager project using progressive complexity.

## Quick Start (once v1 is complete)

```powershell
# 1. Clone / enter the project
cd C:\Users\jobjo\projects\password-manager

# 2. Create and activate venv (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install in editable mode with dev deps
pip install -e ".[dev]"

# 4. The `pwm` command should now be available
pwm --help
pwm init          # sets your master password and creates the vault
pwm generate --length 24 --copy
pwm add --label "Gmail" --username "you@gmail.com" --generate     # flag style
pwm list
pwm search gmail
pwm copy Gmail                                                 # positional style (also works: pwm copy --label Gmail)
pwm get "Gmail Test" --show-password
pwm edit --label "Gmail Test" --notes "Updated via E2E test"   # both styles supported on target commands
pwm change-master
```

The vault file will be at (on Windows):
`%APPDATA%\pwm\vault`

**Back up this file.** It is the only copy of your data. Losing it means losing everything (by design — we have no cloud recovery).

## Development

See `ELI5.md` (5 levels from child to expert), `LEARNINGS.md`, and `SPEC.md`. The setup commands that `pyproject.toml` enables are the standard way to work on the project.

Typical flow:
- Work inside the venv.
- `pwm` command is provided by the console script entry point.
- Run tests with `pytest`.
- Use `--vault-path` during development to avoid touching your real vault.

## Current Feature List (v1 target)

- Strong customizable password generator
- Add / list / search / get / copy / edit / delete entries
- Labels, username, url, notes, tags
- Master password change (full re-encryption)
- Hidden passwords by default in all output
- Rich terminal tables and spinners (while the KDF runs)
- Cross-platform via `platformdirs` + `pyperclip`

## Why This Exists (Educational Note)

This project is intentionally being built slowly and transparently. The primary goal is to understand:

- How modern memory-hard KDFs (Argon2id) actually protect an offline attacker
- Authenticated encryption (AES-GCM) in practice — nonces, AAD, tag, failure modes
- Safe file handling for secrets (atomic writes, header design)
- CLI ergonomics and the real usability vs security trade-offs (clipboard, master password typing, etc.)
- The limits of what Python can guarantee about memory erasure

Every significant choice is recorded in `LEARNINGS.md`.

## License / Usage

Personal / educational use. Do not use this in production for high-value accounts until it has received real security review (v1 is a learning prototype).

## Contributing (to your future self or an agent)

1. Read `AGENTS.md` + `SPEC.md` + `LEARNINGS.md`.
2. Make the smallest change that advances a clear goal.
3. Update `LEARNINGS.md` with any new decision or gotcha.
4. Verify manually on Windows (or your OS) before declaring anything done.
5. Keep the vault file out of git.

---

README updated 2026-06-14 after full E2E testing + automated test suite passing. v1 is now complete and documented at multiple levels of detail.
