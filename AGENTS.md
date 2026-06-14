# AGENTS.md

This file is for any AI coding agent (including future versions of Grok, Claude, Cursor, etc.) working in this repository.

## Mandatory Reading Order (every session)
1. `SPEC.md` — This is the **implementation contract**. Every layer must be implemented exactly to the spec or the spec must be updated first with explicit justification.
2. `LEARNINGS.md` — Current technical decisions, gotchas discovered, and fixes. Most recent entries are at the top.
3. `ELI5.md` — Progressive explanations of the project at five levels of complexity (child → expert). Extremely useful for understanding the intended audience and teaching goals.
4. `ROADMAP.md` — What is intentionally out of scope right now. Do not start items here unless the user explicitly moves them into active work.
5. `README.md` — User-facing status and quick start.
6. Browse the current source under `src/pwm/`.

## Core Non-Negotiables (Security & Education)
- **Never implement cryptographic primitives yourself.** Only use:
  - `cryptography` (AES-GCM via `AESGCM`)
  - `argon2-cffi` (Argon2id **only** via `argon2.low_level.hash_secret_raw` with `Type.ID`)
- The master password is **never** stored, logged, or echoed. Use `getpass.getpass` exclusively.
- Every encryption of the vault uses a **fresh random 16-byte salt** (for Argon2) **and** a **fresh random 12-byte nonce** (for AES-GCM). Nonce reuse with the same key is forbidden.
- Argon2 parameters (time_cost, memory_cost, parallelism) **must** be persisted in the vault header so defaults can evolve without breaking old vaults.
- All writes to the vault file **must** be atomic: write to a sibling `.tmp` file, then `os.replace` (or equivalent).
- The encrypted vault file must remain in the user data directory returned by `platformdirs` (or an explicitly provided `--vault-path`). It is already covered by `.gitignore`.
- Treat this project as a **teaching vehicle**. Every non-trivial decision, parameter choice, or gotcha must be recorded in `LEARNINGS.md` with date and rationale.
- Update `SPEC.md` when the contract changes. Never silently drift from it.
- CLI command name is **exactly** `pwm`.

## Development Process Rules
- Work in small, reviewable increments. Explain what you are doing and why in the chat.
- After any crypto-related change, the agent (or a spawned subagent) must verify roundtrip encryption + explicit failure on wrong master password.
- Before claiming any command or feature "complete", perform a manual end-to-end test on the current OS (Windows/PowerShell here) using a fresh venv.
- Run `pwm --help`, `pwm generate`, `pwm add`, `pwm list`, `pwm copy`, `pwm change-master`, etc.
- Prefer `rich` for all terminal output (tables, panels, spinners during slow KDF). Keep the experience pleasant but never leak secrets.
- Use `typer` for the CLI (with type hints driving help and validation).
- Add or update tests under `tests/` for the crypto and vault layers. CLI can be exercised manually + via `typer.testing` later.
- Never commit any `vault` file, decrypted data, or master passwords (even in tests — use temp dirs).
- When you discover a limitation (clipboard history on Windows, Python GC not zeroing memory, etc.), document it clearly in code comments **and** `LEARNINGS.md`.

## Using Subagents / Parallel Work
- The main agent should implement and explain the core (especially crypto + vault) directly so the human can follow every line.
- Spawn subagents (via the available `spawn_subagent` mechanism) for:
  - Independent code review of security-sensitive modules.
  - "Check-work" verification after a milestone.
  - Parallel exploration (e.g. alternative generator implementations) when the "best-of-n" skill is appropriate.
  - End-to-end verification using the `check-work` or `verification` patterns.
- Any subagent **must** also be instructed (in its prompt) to read SPEC.md + LEARNINGS.md first.
- The orchestrating agent is responsible for reconciling results and keeping the main conversation coherent.

## Tooling & Environment
- Python >= 3.10.
- Modern packaging via `pyproject.toml` + editable install (`pip install -e ".[dev]"`).
- After install the `pwm` console script must be on PATH inside the venv.
- Use `platformdirs` for all user data locations.
- Runtime deps (pinned ranges in pyproject.toml): typer, rich, cryptography, argon2-cffi, pyperclip, platformdirs.
- Dev deps: pytest, ruff (or equivalent), typer[all] if needed for extras.
- On Windows: PowerShell activation (`.venv\Scripts\Activate.ps1`). Clipboard via pyperclip (document its limitations).
- Always activate the venv before running `pwm` or tests during development.

## Communication Style with the Human
- This project exists to teach as much as to be useful. Explain **why** for every decision, trade-off, and library choice.
- When the user asks a question, answer directly and offer to go deeper on any topic (Argon2 parameter selection, AES-GCM nonce rules, atomic file semantics on Windows, clipboard attack surface, etc.).
- If something in SPEC.md feels ambiguous or a proposed change would violate a security invariant, stop and ask the user before proceeding.

## What "Done" Looks Like for v1
- A working `pwm` command that can initialize a vault, generate passwords, add/list/search/copy entries, and change the master password.
- All behavior matches SPEC.md.
- `LEARNINGS.md`, `ROADMAP.md`, and `AGENTS.md` are up to date.
- Manual end-to-end verification has been performed and recorded.
- No plaintext secrets ever touch disk except inside the properly encrypted vault.

Follow these rules strictly. The human will notice and correct deviations.

Last updated: 2026-06-14 (initial)
