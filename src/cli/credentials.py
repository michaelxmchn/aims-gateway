"""Encrypted private-key storage for AIMS developers.

Stores the developer's ECDSA private key as an Ethereum keystore v3 JSON
file at ``~/.aims/credentials``, encrypted with a user-chosen password.

Uses ``eth_account.Account.encrypt()`` / ``Account.decrypt()`` so the
keystore is compatible with MetaMask / Geth import.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

CREDENTIALS_DIR = Path.home() / ".aims"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials"


def _ensure_dir() -> None:
    """Create ``~/.aims/`` with ``0o700`` if it does not exist."""
    CREDENTIALS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def _set_private_permissions(path: Path) -> None:
    """Restrict *path* to owner-only read/write (0o600)."""
    path.chmod(0o600)


def store_private_key(private_key_hex: str, password: str) -> None:
    """Encrypt and persist *private_key_hex* to ``~/.aims/credentials``.

    Args:
        private_key_hex: Hex-encoded ECDSA private key (with or without 0x).
        password: Encryption password for the keystore file.

    Raises:
        ValueError: *private_key_hex* is not a valid key.
        OSError: ``~/.aims/`` is not writable.
    """
    from eth_account import Account

    acct = Account.from_key(private_key_hex)
    keystore = Account.encrypt(acct.key, password)

    _ensure_dir()
    CREDENTIALS_FILE.write_text(json.dumps(keystore, indent=2), encoding="utf-8")
    _set_private_permissions(CREDENTIALS_FILE)


def load_private_key(password: str) -> str:
    """Decrypt and return the hex-encoded private key from ``~/.aims/credentials``.

    Args:
        password: The encryption password.

    Returns:
        Hex-encoded private key (``0x``-prefixed, 64 hex chars after prefix).

    Raises:
        FileNotFoundError: credentials file does not exist.
        ValueError: wrong password or corrupt keystore.
    """
    from eth_account import Account

    keystore_raw = CREDENTIALS_FILE.read_text(encoding="utf-8")
    keystore: dict = json.loads(keystore_raw)
    private_key_bytes = Account.decrypt(keystore, password)
    return private_key_bytes.hex()


def credentials_exist() -> bool:
    """Check whether ``~/.aims/credentials`` exists and is non-empty."""
    return CREDENTIALS_FILE.is_file() and CREDENTIALS_FILE.stat().st_size > 0


def remove_credentials() -> None:
    """Delete ``~/.aims/credentials`` if it exists."""
    if CREDENTIALS_FILE.is_file():
        CREDENTIALS_FILE.unlink()


def prompt_password(confirm: bool = False) -> str:
    """Prompt the user for a keystore password via ``getpass``.

    Args:
        confirm: If True, prompt twice and verify they match.

    Returns:
        The confirmed password string.
    """
    pw = getpass.getpass("Keystore password: ")
    if confirm:
        pw2 = getpass.getpass("Confirm password: ")
        if pw != pw2:
            raise ValueError("Passwords do not match")
    return pw
