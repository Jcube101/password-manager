# ELI5.md — Password Manager Explained at 5 Levels

This file explains the `pwm` password manager project using progressive complexity.  
Start at the level that matches you. Each level builds on the previous one.

---

## Level 1: Explain Like I'm 5 (a little kid)

Imagine you have a super-secret diary.

You write all your important secrets in it (like the passwords for your favorite games and websites).

But this diary has a **magic lock**. The only way to open the lock is with your special "master password" — a long, silly sentence only you know, like "MyDogLovesPizzaOnTuesdays42!".

The diary lives in a special box on your own computer. If a bad kid (or grown-up) steals the box, they can't read what's inside because it's all scrambled up with special magic math. They would have to guess your master password, and the magic makes guessing take forever — like trying to count every grain of sand on a beach one by one.

You talk to the diary using simple commands on your computer, like:

- "Put this new password in the box for Gmail"
- "Show me the password for Netflix" (but it only shows it for a second or lets you copy it safely)
- "Make me a brand new strong password"

When you're done, you lock the box again. Only you with the master password can ever open it.

The box never talks to the internet. It stays right on your computer. If you lose the box file, your secrets are gone forever — so you should make a backup copy of the box somewhere safe.

That's the whole idea: one locked box, one master key you remember, and everything else stays secret even if someone steals the box.

---

## Level 2: A Curious Kid or Teenager Who Likes Computers

`pwm` (short for password manager) is a command-line tool you run in PowerShell or Terminal.

It stores all your website/app passwords in **one single encrypted file** on your computer (usually in a hidden folder like `AppData\Local\pwm\vault` on Windows).

You only have to remember **one strong master password**. Everything else is locked inside that file using real cryptography (fancy math that computers are good at but humans aren't).

### What you can do with it

```powershell
pwm init                    # Create the locked box (first time only)
pwm generate --length 20    # Make a strong random password
pwm add --label "Gmail" --username "you@gmail.com" --generate --tag email
pwm list                    # See all your entries (passwords hidden)
pwm search gmail            # Find things quickly
pwm copy "Gmail"            # Copy the password to clipboard (with a warning)
pwm get "Gmail" --show-password
pwm edit "Gmail" --notes "My main email"
pwm delete "OldService" --yes
pwm change-master           # Change your master password (re-locks everything)
```

### Why it's safer than just remembering passwords or using a notebook

- The file is **encrypted** with two strong algorithms:
  - Argon2id: Turns your master password into a super-hard-to-guess key (it deliberately takes a second or two and uses lots of memory).
  - AES-GCM: Actually scrambles the data so only the right key can unscramble it, and it also checks that nobody tampered with the file.
- No internet. No company can get hacked and leak your passwords.
- If someone copies the vault file, they still need your master password. The math makes brute-force attacks extremely slow.
- You control everything. You decide where the file lives and how you back it up.

**Downsides a kid can understand**: You have to type the master password every time you want to use it (for safety). The clipboard warning is real — other programs on your computer could potentially see what you copied. If you forget the master password or lose the vault file, your passwords are gone forever.

---

## Level 3: Beginner Programmer or Power User Who Wants to Understand the Tool

This is a small, educational, local-only CLI password manager written in Python.

### High-level architecture

- **Single encrypted blob** (`vault` file). No database, no cloud sync.
- **Master password** is never stored. It is turned into a 256-bit key using Argon2id every time you run a command that needs the data.
- All entries (label, username, password, url, notes, tags, timestamps) live as JSON inside the encrypted blob.
- The CLI is built with **Typer** (nice commands + help) + **Rich** (pretty tables and spinners while the slow key derivation runs).

### Key commands and flow

1. `pwm init` — Creates the vault file with your master password.
2. Everyday use: `pwm add --label ...`, `pwm list`, `pwm copy <label>`.
3. Both styles work for labels on most commands:
   - Positional (short): `pwm copy Gmail`
   - Explicit flag: `pwm copy --label Gmail` or `pwm copy -l Gmail`
4. `pwm change-master` decrypts with the old master, then re-encrypts everything with a fresh salt + nonce under the new master.

### Security model (beginner version)

- **Threats it protects against**: Someone steals your laptop or the vault file. Offline brute-force is made very expensive by Argon2id.
- **Threats it does NOT protect against**: Keyloggers while you type the master password, malware running while the vault is unlocked in memory, or you reusing the master password elsewhere.
- **Clipboard** is inherently risky on desktops — the tool warns you every time.

The project deliberately stays simple so the code is easy to audit and understand.

---

## Level 4: Intermediate Developer — Architecture & Implementation Details

### Directory structure (v1)

```
src/pwm/
├── __init__.py
├── cli.py          # Typer app, all commands, getpass prompts, Rich output
├── crypto.py       # Argon2id key derivation + AES-256-GCM encrypt/decrypt + header format
├── generator.py    # secrets-based strong password generator (no random module!)
├── models.py       # Entry dataclass + ISO timestamps
├── vault.py        # The heart: platformdirs location, atomic writes, CRUD, unlock/lock, change-master
└── clipboard.py    # Thin pyperclip wrapper with explicit security warnings

tests/
├── test_crypto.py
├── test_generator.py
├── test_vault.py
└── test_cli.py     # Uses typer.testing.CliRunner for non-interactive paths
```

### The on-disk vault format (exactly as implemented)

```
[4 bytes]  "PWM1" magic + format version
[1 byte]   Format version (1)
[4 bytes]  Argon2 time_cost (uint32 LE)
[4 bytes]  Argon2 memory_cost in KiB (uint32 LE)
[1 byte]   Argon2 parallelism
[16 bytes] Random salt (for Argon2)
[12 bytes] Random nonce (for AES-GCM)
[rest]     AES-GCM ciphertext (plaintext JSON + 16-byte auth tag)
```

Associated data (AAD) binds the header prefix to the ciphertext.

**Every save** (including change-master) uses a **brand new salt and nonce**. This is mandatory for AES-GCM safety.

### Important implementation choices

- **Atomic writes**: Write to `vault.tmp`, `fsync`, then `os.replace`. Prevents corrupt vault on crash.
- **In-memory only** after successful unlock. `lock()` does best-effort `del` + `gc.collect()`.
- **No per-entry encryption** — the whole list of entries is serialized to JSON and encrypted as one blob. Simple and auditable.
- **Argon2 params are stored in the header** so we can raise the defaults later without breaking old vaults.
- Default params (64 MiB memory, time=3, parallelism=4) aim for ~1–2.5s on a typical desktop while providing strong memory-hardness.
- Password generator uses only `secrets` + explicit character classes + exclude list.

### CLI dual interface

Most label-taking commands accept the value either as a positional argument or via `--label` / `-l`. This was added after initial testing because users (and early planning notes) expected the flag style on `add`, while positional feels natural for `copy` / `get`.

### Testing

- Crypto has roundtrip + wrong-master + tamper tests.
- Vault has create/unlock/CRUD/change-master/atomicity tests.
- CLI tests cover help text, version, generate, dual-label help, etc. (non-interactive paths).

---

## Level 5: Expert / Security Engineer / Future Maintainer

### Cryptographic details & why they matter

- **Argon2id** (not Argon2i or Argon2d alone) via `argon2_cffi.low_level.hash_secret_raw(..., Type.ID)`. 32-byte output fed directly to AES-256-GCM.
- **AES-GCM** via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. 12-byte random nonce (never reused with same key). 16-byte tag. AAD = first 30 bytes of header (binds params + salt).
- Nonce reuse with the same key on GCM is catastrophic (loss of confidentiality + authenticity). The code generates fresh nonces on every `encrypt_vault` call.
- Master password stretching is the primary defense against offline attacks on a stolen vault file. Memory-hardness (Argon2) resists GPUs/ASICs far better than PBKDF2 or bcrypt for this use case.
- The vault file is **authenticated encryption end-to-end**. Wrong master or any tampering → generic `VaultDecryptionError` ("Wrong master password or the vault file is corrupted.") — no information leakage.

### Subtle implementation realities

- **Python memory clearing is best-effort only**. `del key; gc.collect()` helps but CPython's string interning, reference counting, and lack of secure zeroization mean secrets can linger in process memory. Documented limitation.
- **Atomicity**: `os.replace` after `fsync` on the temp file gives good crash safety on same-volume moves (works on Windows and POSIX).
- **Clipboard surface**: `pyperclip` is used, but the wrapper explicitly documents the real risks (other processes, Windows clipboard history via Win+V, no reliable auto-clear). This is intentional education, not marketing.
- **Master prompt UX**: Every sensitive command calls `getpass.getpass`. No agent, no keyring, no env-var fallback by default. This is the biggest real-world friction (and the biggest practical attack surface — shoulder surfing or keylogger during entry).
- **File permissions**: The tool does not aggressively set Windows ACLs or Unix 0600 in v1 (relies on user_data_dir location + user responsibility).

### Design trade-offs made for education + auditability

- Single encrypted file instead of sqlcipher or age-encrypted SQLite. One blob you can `xxd` and understand completely.
- No OS keyring / DPAPI integration in v1 (would have complicated the "simple auditable" story).
- Whole-vault re-encryption on every mutation and on `change-master` (simple, no per-item keys).
- JSON inside the blob (human readable once decrypted — huge for debugging and learning).
- Conservative, well-known libraries only (`cryptography`, `argon2-cffi`). Zero custom crypto.

### Known weaknesses / future work (see ROADMAP.md)

- Master password entry is the weak link in practice.
- Clipboard is leaky by nature on desktops.
- No TOTP, no history of old passwords, no export/import (yet).
- The current Argon2 defaults are reasonable for 2026 desktops but should be tunable and documented.
- Future nice-to-haves: platform keyring integration (with strong warnings), TOTP support, passphrase generator, fuzzy search, formal property-based tests.

### How to audit / extend this code

1. Read `SPEC.md` first — it is the contract.
2. Start in `crypto.py` + its tests. Verify that wrong keys and tampering always produce the same generic error.
3. Then `vault.py` — focus on the header format, atomic write path, and the fact that `save()` always re-derives with fresh material.
4. The CLI layer is intentionally thin — all real logic lives in the lower layers.

This project is deliberately small so a motivated person can read and understand the entire security boundary in an afternoon.

---

**Project philosophy (applies at every level)**:  
Be conservative with cryptography. Never implement primitives yourself. Make the code easy to audit. Make the limitations and trade-offs explicit. The goal is as much "teach the reader" as "be a useful daily tool."

If you're at Level 5 and want to contribute, the best starting points are usually in `LEARNINGS.md` (real decisions and gotchas) and `ROADMAP.md` (scoped future work).

Enjoy the rabbit hole.
