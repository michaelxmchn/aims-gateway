"""Binary obfuscation stub for AIMS skill distribution.

Produces a ``wrapper.so`` binary stub as a placeholder.  In production
this is replaced by PyArmor / Cython compilation or a hardware security
module integration.
"""

from __future__ import annotations

import struct
from pathlib import Path

import click


def obfuscate_entrypoint(
    entry_point: Path,
    *,
    output_dir: Path | None = None,
) -> Path:
    """Generate a mock ``wrapper.so`` binary stub.

    The stub embeds the original entry-point filename so a future
    obfuscation pass can locate the source.

    Returns:
        Path to the generated ``wrapper.so`` (always placed in *output_dir*).

    Raises:
        FileNotFoundError: *entry_point* does not exist.
    """
    if output_dir is None:
        output_dir = Path.cwd() / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not entry_point.is_file():
        raise FileNotFoundError(f"Entry point not found: {entry_point}")

    so_path = output_dir / "wrapper.so"

    # Build a minimal ELF stub (so the file is recognisable as a library)
    #   ELF header (64-bit little-endian) + reference to the entry point
    elf_hdr = struct.pack(
        "<4sBBBBBBBBIQQIBHHHHHH",
        b"\x7fELF",          # magic
        2,                   # 64-bit
        1,                   # little-endian
        1,                   # ELF version
        0,                   # OS/ABI
        0, 0, 0,             # padding
        0,                   # type (ET_NONE — relocatable)
        0x3E,                # machine x86_64
        1,                   # version
        0, 0, 0, 0, 0, 0,   # entry / phoff / shoff / flags / ehsize
        0, 0,                # phentsize / phnum
        0, 0,                # shentsize / shnum
        0, 0,                # shstrndx
    )
    payload = (
        elf_hdr
        + b"AIMS_Obfuscated_Stub\n"
        + f"Original: {entry_point.name}\n".encode()
    )
    # Pad to at least 4 KB so the file seems credible
    payload = payload.ljust(4096, b"\x00")

    so_path.write_bytes(payload)
    click.echo(click.style(f"✔ Obfuscated stub → {so_path}", fg="green"))
    return so_path
