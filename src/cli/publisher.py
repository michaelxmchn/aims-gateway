"""Full publish pipeline for AIMS skill distribution.

Orchestrates: validate config → load credentials → obfuscate → encrypt
→ sign → package → upload → register metadata, including a detailed
ASCII audit table with the 5% platform-fee split.
"""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path

import click
import requests

from src.cli.encryptor import encrypt_directory, generate_key
from src.cli.obfuscator import obfuscate_entrypoint
from src.cli.signer import sign_skill


def publish_skill(
    config_path: Path,
    *,
    gateway_override: str | None = None,
    entry_point_override: str | None = None,
) -> None:
    """Run the full publish pipeline (8 steps)."""
    from src.cli.schema import AIMSConfig
    from src.cli.credentials import credentials_exist, load_private_key, prompt_password

    click.echo()
    click.echo(click.style("✦ AIMS Skill Publish Pipeline", bold=True))
    click.echo("─" * 50)

    # ── Step 1: Validate config ─────────────────────────────────────────
    click.echo(click.style("Step 1/8: Validating config...", bold=True))
    if not config_path.is_file():
        click.echo(click.style(f"✖ {config_path} not found. Run `aims-cli init` first.", fg="red"))
        return

    try:
        config = AIMSConfig.from_json_file(config_path)
    except Exception as exc:
        from src.cli.main import _print_validation_errors
        _print_validation_errors(exc)
        return

    gateway_url = (gateway_override or config.gateway_url).rstrip("/")
    entry_point = Path(entry_point_override) if entry_point_override else Path(config.entry_point)
    split = config.monetization.revenue_split()
    quadrant = config.monetization.quadrant_label()

    click.echo(click.style(f"✔ Config valid: {config.skill_id} v{config.version}", fg="green"))

    # ── Step 2: Load credentials ────────────────────────────────────────
    click.echo(click.style("Step 2/8: Loading developer key...", bold=True))
    if not credentials_exist():
        click.echo(click.style("✖ No credentials found. Run `aims-cli login` first.", fg="red"))
        return

    password = prompt_password()
    try:
        private_key_hex = load_private_key(password)
    except ValueError:
        click.echo(click.style("✖ Wrong password or corrupt keystore. Try again.", fg="red"))
        return
    click.echo(click.style("✔ Developer key loaded", fg="green"))

    # ── Prepare dist directory ──────────────────────────────────────────
    dist_dir = Path.cwd() / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)

    # ── Step 3: Obfuscate ───────────────────────────────────────────────
    click.echo(click.style("Step 3/8: Obfuscating entry point...", bold=True))
    if not entry_point.is_file():
        click.echo(click.style(f"✖ Entry point not found: {entry_point}", fg="red"))
        return
    try:
        obfuscated = obfuscate_entrypoint(entry_point, output_dir=dist_dir)
    except FileNotFoundError as exc:
        click.echo(click.style(f"✖ {exc}", fg="red"))
        return
    click.echo(click.style(f"✔ Obfuscated → {obfuscated.name}", fg="green"))

    # ── Step 4: Encrypt ─────────────────────────────────────────────────
    click.echo(click.style("Step 4/8: Encrypting source (AES-256-GCM)...", bold=True))
    key = generate_key()
    logic_enc = dist_dir / "logic.enc"
    key_hash = encrypt_directory(Path.cwd(), key, logic_enc)
    click.echo(click.style(f"✔ Encrypted → {logic_enc.name}  key_hash={key_hash[:16]}...", fg="green"))

    # ── Step 5: Sign ────────────────────────────────────────────────────
    click.echo(click.style("Step 5/8: Signing provenance (EIP-191)...", bold=True))
    signature_result = sign_skill(
        skill_id=config.skill_id,
        key_hash=key_hash,
        price=config.price_per_task_usdc,
        private_key_hex=private_key_hex,
    )
    click.echo(click.style(f"✔ Signed by {signature_result['signer']}", fg="green"))

    # ── Step 6: Package ─────────────────────────────────────────────────
    click.echo(click.style("Step 6/8: Packaging dist.zip...", bold=True))
    dist_zip = Path.cwd() / "dist.zip"
    _build_zip(dist_dir, dist_zip, obfuscated, logic_enc)
    click.echo(click.style(f"✔ dist.zip created ({_human_size(dist_zip.stat().st_size)})", fg="green"))

    # ── Step 7: Upload ──────────────────────────────────────────────────
    click.echo(click.style("Step 7/8: Uploading dist.zip...", bold=True))
    upload_url = f"{gateway_url}/api/skills/upload"
    try:
        storage_url = _upload_dist(dist_zip, upload_url)
    except requests.RequestException as exc:
        click.echo(
            click.style(
                f"✖ Upload failed: {exc}\n  dist.zip preserved at {dist_zip} for manual retry.",
                fg="red",
            )
        )
        return
    click.echo(click.style(f"✔ Uploaded → {storage_url}", fg="green"))

    # ── Step 8: Register metadata ───────────────────────────────────────
    click.echo(click.style("Step 8/8: Registering metadata...", bold=True))
    try:
        _register_metadata(config, storage_url, private_key_hex, gateway_url)
    except requests.RequestException as exc:
        click.echo(
            click.style(
                f"✖ Metadata registration failed: {exc}\n"
                f"  dist.zip preserved at {dist_zip}. "
                f"Run publish again to retry registration.",
                fg="red",
            )
        )
        return

    # ── ASCII audit table ──────────────────────────────────────────────
    _print_audit_table(config, quadrant, split, signature_result, storage_url, dist_zip)

    click.echo()
    click.echo(click.style("✔ Publish complete! Your skill is live on the AIMS network.", fg="green", bold=True))


# ── ASCII audit table ────────────────────────────────────────────────────────


def _print_audit_table(
    config: "AIMSConfig",  # noqa: F821
    quadrant: str,
    split: dict[str, float],
    signature_result: dict,
    storage_url: str,
    dist_zip: Path,
) -> None:
    """Print a detailed ASCII audit table with the 5% platform fee split."""
    price = config.price_per_task_usdc
    dev_share = price * split["developer"] / 100.0
    worker_share = price * split["worker"] / 100.0
    platform_share = price * split["platform"] / 100.0

    click.echo()
    click.echo(click.style("╔═══════════════════════════════════════════════════════════╗", bold=True))
    click.echo(click.style("║              AIMS Settlement Audit Summary               ║", bold=True))
    click.echo(click.style("╚═══════════════════════════════════════════════════════════╝", bold=True))
    click.echo()
    click.echo(f"  Skill:            {config.skill_id} v{config.version}")
    click.echo(f"  Quadrant:          {quadrant}  ({config.monetization.function_type} + {config.monetization.billing_mode})")
    click.echo(f"  Developer Wallet:  {config.developer_wallet}")
    click.echo(f"  EIP-191 Signer:    {signature_result['signer']}")
    click.echo(f"  Signature:         {signature_result['signature'][:42]}...")
    click.echo()

    # ── Revenue split table ─────────────────────────────────────────────
    click.echo(click.style("  ┌──────────────────────┬──────────┬────────────┐", bold=True))
    click.echo(click.style("  │ Party                │    Share │     Amount  │", bold=True))
    click.echo(click.style("  ├──────────────────────┼──────────┼────────────┤", bold=True))
    dev_pct = f"{split['developer']:5.1f}%"
    dev_amt = f"${dev_share:>8.4f}"
    click.echo(f"  │ Developer ({split['developer']:.0f}%)           │ {dev_pct}  │ {dev_amt}  │")
    if split["worker"] > 0:
        wrk_pct = f"{split['worker']:5.1f}%"
        wrk_amt = f"${worker_share:>8.4f}"
        click.echo(f"  │ Worker Node ({split['worker']:.0f}%)          │ {wrk_pct}  │ {wrk_amt}  │")
    else:
        click.echo(click.style("  │ Worker Node (0%)        │  0.0%  │    —       │", fg="bright_black"))
    plt_pct = f"{split['platform']:5.1f}%"
    plt_amt = f"${platform_share:>8.4f}"
    click.echo(f"  │ AIMS Platform Treasury  │ {plt_pct}  │ {plt_amt}  │")
    click.echo(click.style("  └──────────────────────┴──────────┴────────────┘", bold=True))
    click.echo()

    # ── Fee summary ────────────────────────────────────────────────────
    click.echo(f"  Price per task:   ${price:.4f} USDC")
    click.echo(f"  Total fees (5%):  ${platform_share:.4f} USDC")
    click.echo(
        click.style(
            f"  Net to developer: ${dev_share:.4f} USDC" + (f"  (+ {worker_share:.4f} to Worker)" if worker_share > 0 else ""),
            fg="green",
        )
    )
    click.echo()

    # ── Delivery info ───────────────────────────────────────────────────
    click.echo(click.style("  ┌─────────────────────────────────────────────────────┐", bold=True))
    click.echo(click.style("  │  Delivery Summary                                   │", bold=True))
    click.echo(click.style("  ├─────────────────────────────────────────────────────┤", bold=True))
    click.echo(f"  │  Artifact:     {str(dist_zip):<43s}  │")
    click.echo(f"  │  Storage:      {storage_url:<43s}  │")
    click.echo(f"  │  Gateway:      {config.gateway_url:<43s}  │")
    click.echo(f"  │  Rate Limit:   {'N/A' if config.monetization.rate_limit_per_day is None else str(config.monetization.rate_limit_per_day) + ' tasks/day':<43s}  │")
    click.echo(click.style("  └─────────────────────────────────────────────────────┘", bold=True))


# ── Internal helpers ────────────────────────────────────────────────────────


def _build_zip(dist_dir: Path, output: Path, obfuscated: Path, logic_enc: Path) -> None:
    """Create ``dist.zip`` containing the obfuscated artifact and encrypted logic."""
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(obfuscated, arcname=obfuscated.name)
        zf.write(logic_enc, arcname=logic_enc.name)


def _upload_dist(zip_path: Path, upload_url: str) -> str:
    """Upload *zip_path* via multipart POST.

    Returns the storage URL string (from the response body or the
    upload URL itself).
    """
    with open(zip_path, "rb") as f:
        resp = requests.post(
            upload_url,
            files={"dist": (zip_path.name, f, "application/zip")},
            timeout=300,
        )
    resp.raise_for_status()
    data: dict = resp.json()
    skill_id = data.get("skill_id", "")
    if skill_id:
        return f"{upload_url.rstrip('/api/skills/upload')}/api/skills/{skill_id}/logic"
    return upload_url


def _register_metadata(
    config: "AIMSConfig",
    storage_url: str,
    private_key_hex: str,
    gateway_url: str,
) -> None:
    """Register skill metadata on the gateway via EIP-191 signed request."""
    from eth_account import Account
    from eth_account.messages import encode_defunct

    body = {
        "skill_id": config.skill_id,
        "contributor_address": config.developer_wallet,
        "encrypted_source": storage_url,
    }
    body_bytes = json.dumps(body, separators=(",", ":")).encode()

    ts = str(int(time.time()))
    signable = encode_defunct(primitive=body_bytes)
    acct = Account.from_key(private_key_hex)
    signed = Account.sign_message(signable, acct.key)

    headers = {
        "X-Wallet-Address": config.developer_wallet,
        "X-Signature": signed.signature.hex(),
        "X-Timestamp": ts,
        "Content-Type": "application/json",
    }

    resp = requests.post(
        f"{gateway_url}/api/skills/register-metadata",
        headers=headers,
        data=body_bytes,
        timeout=60,
    )

    if resp.status_code == 409:
        click.echo(
            click.style(
                f"⚠  Metadata for '{config.skill_id}' already registered (HTTP 409).",
                fg="yellow",
            )
        )
        return

    resp.raise_for_status()


def _human_size(bytes_: int) -> str:
    """Format byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} TB"
