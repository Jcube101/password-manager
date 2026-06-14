# password-manager

Quick local-first password manager prototype.

**Status**: Brand new. Working in the safe `projects/` folder with local-only git. No GitHub remote yet.

## Goals for v1 (keep it quick and safe)
- Store credentials locally in an encrypted vault
- Strong master password (never stored in plaintext)
- Basic CRUD: add, get, list, update, delete entries
- Copy password to clipboard securely
- No network / no cloud sync in v1
- Easy to audit

## Security Notes (important)
- We will **not** roll our own crypto primitives.
- Use well-audited libraries (e.g. Python `cryptography`, `argon2-cffi`, or platform keyring where possible).
- Vault file must be in .gitignore.
- Clear sensitive data from memory where practical.
- Consider OS keychain integration later (Windows DPAPI / Credential Manager).

## Tech choices (to decide)
- Language/runtime: Python (fast for prototype) or Node/TS?
- Storage: Single encrypted file (JSON + AES-GCM) or embedded DB?
- CLI interface (argparse / click / typer) or minimal web UI?

## Next steps
1. Decide on language + minimal feature set.
2. Set up virtualenv / dependencies.
3. Implement master password + key derivation.
4. Implement vault encryption / decryption.
5. Build the command interface.

This is intentionally staying in `projects/password-manager` until it proves useful. Only then consider moving/copying to the real `Github/` folder and adding a remote.

## Safety
Global hooks are installed to prevent accidental `gh repo delete` or mass deletion of the `Github/` or `projects/` trees, even in auto-approve modes.
