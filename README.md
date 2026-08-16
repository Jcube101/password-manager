# pwm — Local-First Password Manager (CLI)

Quick, auditable, educational password manager that stores everything in a single encrypted file on your machine.

**Status**: v1 complete and tested.

- Full E2E interactive run on Windows (init → add/generate in both label styles → list/search/get/copy/edit/delete → change-master) succeeded.
- All 28 automated tests pass (`pytest -q`).
- Dual label interface (`pwm copy Gmail` or `pwm copy --label Gmail`) is fully supported.

See `ELI5.md` for explanations at 5 levels of complexity (kid → expert).  
See `LEARNINGS.md` for the build log, decisions, and testing notes.  
See `SPEC.md` for the implementation contract.

The project is intentionally educational first: small, auditable, conservative crypto, explicit limitations.

## How this feels day to day

`pwm` is a **command-line locker**, not a browser extension.

You remember **one master password**. Every other secret lives in one encrypted file on this computer. When you need a password, you open a terminal, unlock the vault (type the master), and copy the entry you want. There is no tray icon, no auto-fill, no cloud sync, and no "stay logged in." That is the point: the process unlocks, does one job, and exits.

Typical rhythm:

1. Need a password → `pwm copy Gmail`
2. Type your master (unlock takes about 1–2 seconds — that delay is Argon2 working)
3. Paste into the site, then treat the clipboard as dirty
4. Done. The vault is locked again because the process ended.

## First-time setup

```powershell
# 1. Clone / enter the project
cd C:\Users\jobjo\Github\password-manager

# 2. Create and activate a venv (Windows PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install so the `pwm` command exists
pip install -e ".[dev]"

# 4. Create the vault (you will be asked for a master password twice)
pwm init
```

Pick a **long master passphrase you can actually type**, not a cute 8-character password. Something like a silly sentence only you know. If you forget it, the vault is gone. There is no reset, no email, no recovery code.

Then confirm where the file actually landed:

```powershell
pwm info
```

That path is the source of truth. On Windows it is usually under your local user-data directory (often `%LOCALAPPDATA%\pwm\...`). Copy that file somewhere safe (USB, encrypted backup, another disk). **It is the only copy of your data.**

## Make `pwm` available in every terminal

After `pip install -e .` inside the project venv, `pwm` only exists when that venv is active. For daily use, add a small PowerShell wrapper so you do not have to `cd` and activate every time.

```powershell
# Open your PowerShell profile
notepad $PROFILE
```

Put this function in the file (replace the path if your clone lives elsewhere):

```powershell
function pwm {
    & "C:\Users\jobjo\Github\password-manager\.venv\Scripts\python.exe" -m pwm @args
}
```

Reload with `. $PROFILE` (or open a new terminal), then `pwm --help` should work from any directory.

**Use `python.exe -m pwm`, not `pwm.exe`.** On Windows, `pwm.exe` is a tiny launcher that hard-codes the path to `python.exe` from the moment you ran `pip install`. If the project (or the `.venv` folder) is ever moved — this repo used to live under `C:\Users\jobjo\projects\` — that launcher still looks in the old place and dies with `Fatal error in launcher: Unable to create process`. Calling the interpreter with `-m pwm` skips that stub.

If you *do* move the repo later, recreate the venv in the new location rather than copying `.venv`:

```powershell
cd C:\Users\jobjo\Github\password-manager
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Editable installs also bake in the old project path (`__editable__.pwm-0.1.0.pth`). A moved `.venv` will then say `No module named pwm` until you reinstall.

## Daily command cheat sheet

Every command that reads or writes secrets will prompt `Master password:` and show a spinner while Argon2 runs. `generate` and `info` do **not** need the vault.

| What you want | Command |
|---|---|
| Copy a password (the daily workhorse) | `pwm copy Gmail` |
| Same thing, flag style | `pwm copy --label Gmail` or `pwm copy -l Gmail` |
| Look something up when you forgot the label | `pwm search netflix` |
| See everything (passwords hidden) | `pwm list` |
| See only work stuff | `pwm list --tag work` |
| Show one entry, still hide the password | `pwm get Gmail` |
| Show the password on screen (shoulder-surf risk) | `pwm get Gmail --show-password` |
| New account, generate a strong password | `pwm add --label Notion --username you@x.com --generate --tag work` |
| New account, you will type the existing password | `pwm add --label Bank --username you` (then type it hidden) |
| Update notes / username / url | `pwm edit Gmail --notes "recovery phone on file"` |
| Rename an entry | `pwm edit Gmail --new-label "Gmail personal"` |
| Change a stored password | `pwm generate` then `pwm edit Gmail --password "..."` (see warning below) |
| Delete an entry | `pwm delete OldForum` (asks to confirm) or `pwm delete OldForum --yes` |
| Change the master password | `pwm change-master` |
| Where is my vault? | `pwm info` |
| Just make a password, do not store it | `pwm generate --length 24` |
| Make one and copy it | `pwm generate --length 24 --copy` |

Labels on `get` / `copy` / `edit` / `delete` accept either style. `add` always uses `--label` / `-l` because it has many fields.

Exact lookup (`copy`, `get`, `edit`, `delete`) is **case-sensitive**. Search is **case-insensitive** and matches label, username, URL, notes, and tags.

## A typical week

**Monday — log into email**

```powershell
pwm copy Gmail
```

Type master → paste into the browser → continue with your day. Prefer copy over `--show-password` so the secret is not sitting in the terminal scrollback.

**Tuesday — sign up for a new tool**

```powershell
pwm add --label "Linear" --username "you@work.com" --url "https://linear.app" --generate --tag work --tag saas
pwm copy Linear
```

`--generate` creates a strong password and stores it. Then copy it once into the signup form.

**Wednesday — "what was that bank site called?"**

```powershell
pwm search bank
pwm list --tag finance
pwm get "First National"
```

**Thursday — rotate a leaked password**

```powershell
pwm generate --length 24
pwm edit GitHub --password "paste-the-generated-value"
```

`--password` on the command line **lands in PowerShell history**. That is the awkward part of v1 `edit`. Prefer generating first, then passing the value only if you accept the history risk — or type it in a throwaway session and clear history afterward (`Remove-Item (Get-PSReadlineOption).HistorySavePath` is the nuclear option). Do **not** make a habit of `pwm add --password hunter2`.

If you are creating a *new* secret, skip `--password` entirely: omit it and either let `add` generate one, or type it at the hidden prompt.

**Friday — tidy up**

```powershell
pwm list
pwm delete "OldForum"
pwm info          # confirm the file you are about to back up
```

Copy the vault file shown by `pwm info` to your backup location. You can copy that file while `pwm` is not running; it is already encrypted.

## Habits that actually matter

- **Type the master every time.** There is no session cache in v1. The 1–2 second unlock is intentional (memory-hard KDF). If that ever feels too annoying, the answer is not a weaker master — see `ROADMAP.md` for a future optional OS-keyring unlock.
- **Never put secrets on the command line if you can avoid it.** `pwm add --password ...` and `pwm edit --password ...` are recorded by the shell. Use `--generate` or the hidden prompt on `add`.
- **Treat the clipboard as public.** Other programs can read it. Windows clipboard history (`Win+V`) may keep the value. Paste, then copy something else (or clear it). `pwm` warns you on every copy on purpose.
- **Name labels the way you think.** `Gmail`, `Chase`, `WiFi home`. Unique, memorable, case-sensitive for exact commands.
- **Use tags as light folders.** `--tag work --tag email`. Then `pwm list --tag work`.
- **Back up the vault file after any important change** (new entries, `change-master`). The file is encrypted; the backup is still only as safe as where you put it.
- **If the master might be leaked, run `pwm change-master`.** That re-encrypts everything with a fresh salt and nonce. Old backups remain unlockable with the *old* master — rotate those too, or destroy them.

## What this will not do

- Fill forms in the browser
- Sync to your phone or another PC (copy the vault file yourself)
- Recover a forgotten master password
- Stay unlocked in the background
- Auto-clear the clipboard after N seconds (not in v1)

Those limits are deliberate. They keep the security story small enough to audit.

## Two vaults (work / personal / testing)

```powershell
pwm --vault-path D:\work-vault init
pwm --vault-path D:\work-vault add --label "Corp SSO" --generate
pwm --vault-path D:\work-vault copy "Corp SSO"
```

`--vault-path` / `-p` is global and useful for a second vault or for development so you never touch the real one.

## Security posture (short version)

- We **never** roll our own crypto primitives.
- Key derivation: Argon2id (`argon2-cffi`). Vault encryption: AES-256-GCM (`cryptography`).
- Fresh random salt + nonce on every save.
- Atomic writes (`vault.tmp` then `os.replace`) so a crash cannot leave a half-written vault.
- Master password is never stored, logged, or echoed (`getpass` only).
- Clipboard and shell history are the real-world weak spots — documented, not pretended away.

See `SPEC.md` for the on-disk format. See `LEARNINGS.md` for why each choice was made. See `ROADMAP.md` for what is out of scope. See `ELI5.md` for the same story at five levels of complexity. See `AGENTS.md` if an AI is helping with future changes.

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

README updated 2026-08-16: day-to-day usage guide, plus a corrected PowerShell wrapper (`python -m pwm` instead of `pwm.exe`) after a moved-venv launcher failure.
