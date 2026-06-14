"""pwm - Local-first educational password manager.

Core package. See SPEC.md for the full implementation contract.
"""

__version__ = "0.1.0"

from .cli import app as cli_app  # entry point target
from .generator import generate_password
from .vault import Vault, get_default_vault_path
from .crypto import (
    encrypt_vault,
    decrypt_vault,
    derive_key,
    VaultDecryptionError,
    ArgonParams,
)

__all__ = [
    "cli_app",
    "generate_password",
    "Vault",
    "get_default_vault_path",
    "encrypt_vault",
    "decrypt_vault",
    "derive_key",
    "VaultDecryptionError",
    "ArgonParams",
]
