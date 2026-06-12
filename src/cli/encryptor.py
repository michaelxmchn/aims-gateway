"""AES-256-GCM encryption for AIMS skill distribution.

Encrypts the core AI logic into ``logic.enc`` using a random 256-bit key.
The key hash (SHA-256) is returned for downstream EIP-191 signing.
"""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
from pathlib import Path


def generate_key() -> bytes:
    """Generate a random 256-bit (32-byte) AES key."""
    return os.urandom(32)


def encrypt_file(input_path: Path, key: bytes, output_path: Path) -> str:
    """Encrypt a single file with AES-256-GCM.

    Writes ``nonce (12 B) || ciphertext`` to *output_path*.

    Returns:
        Hex-encoded SHA-256 hash of *key* (for downstream signing).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    data = input_path.read_bytes()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(nonce + ciphertext)

    return hashlib.sha256(key).hexdigest()


def encrypt_directory(src_dir: Path, key: bytes, output_path: Path) -> str:
    """Recursively collect all ``.py`` files under *src_dir*, tar them,
    and encrypt the tar archive with AES-256-GCM.

    Writes ``nonce (12 B) || ciphertext`` to *output_path*.

    Returns:
        Hex-encoded SHA-256 hash of *key* (for downstream signing).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    # Collect .py files relative to src_dir
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for py_file in sorted(src_dir.rglob("*.py")):
            arcname = py_file.relative_to(src_dir)
            tar.add(py_file, arcname=arcname)

    tar_bytes = buf.getvalue()

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, tar_bytes, None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(nonce + ciphertext)

    return hashlib.sha256(key).hexdigest()
