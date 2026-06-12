"""Binary obfuscation stub for AIMS skill distribution.

Produces a ``wrapper.so`` binary stub as a placeholder.  In production
this is replaced by PyArmor / Cython compilation or a hardware security
module integration.
"""

from __future__ import annotations

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

    payload = (
        # ELF magic (4 bytes) so Unix ``file`` recognises it as ELF
        b"\x7fELF"
        # AIMS stub marker + reference to original source
        + b"\nAIMS_Obfuscated_Stub\n"
        + f"Original: {entry_point.name}\n".encode()
        # Pad to 4 KB
        ).ljust(4096, b"\x00")

    so_path.write_bytes(payload)
    click.echo(click.style(f"✔ Obfuscated stub → {so_path}", fg="green"))
    return so_path
