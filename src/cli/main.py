#!/usr/bin/env python3
"""AIMS Contributor CLI — init, login, and publish skills.

Commands:
  init    Interactive 2×2 matrix walkthrough — ``aims.config.json``.
  login   Encrypt and persist a developer private key locally.
  publish Full DRM pipeline: obfuscate, encrypt, sign, package, register.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from src.cli.schema import AIMSConfig, MonetizationConfig


# ── Helpers ────────────────────────────────────────────────────────────────


def _print_validation_errors(exc) -> None:
    """Print Pydantic ``ValidationError`` details in a structured format."""
    click.echo(click.style("✖ Validation failed:", fg="red", bold=True))
    for err in exc.errors():
        field = " → ".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "")
        click.echo(f"  {click.style(field, bold=True)}: {msg}")
    click.echo()


# ── init ────────────────────────────────────────────────────────────────────


REVENUE_MATRIX_HELP = """
Revenue Split Matrix
  Q1  worker_collab + pay_per_task    →  70% Developer / 25% Worker / 5% Platform
  Q2  worker_collab + subscription     →  95% Developer /  0% Worker / 5% Platform
  Q3  direct_skill   + pay_per_task    →  95% Developer /  0% Worker / 5% Platform
  Q4  direct_skill   + subscription    →  95% Developer /  0% Worker / 5% Platform

Platform Treasury always takes a strict 5%% cut across all quadrants.
"""


@click.command()
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing aims.config.json without prompting.",
)
def init(force: bool) -> None:
    """Interactive wizard — create aims.config.json based on the 2×2 matrix.

    Guides you through function type, billing mode, and 7 configuration
    fields, then validates and writes a prettified JSON file.
    """
    config_path = Path.cwd() / "aims.config.json"

    if config_path.exists() and not force:
        click.echo(f"  {config_path} already exists. Use --force to overwrite.")
        return

    click.echo(click.style("✦ AIMS Config Initialization", bold=True))
    click.echo(click.style("✦ Revenue Matrix (2×2)", bold=True))
    click.echo(REVENUE_MATRIX_HELP.strip())
    click.echo("─" * 50)

    # ── 1. Monetization matrix ──────────────────────────────────────────
    function_type = click.prompt(
        "Function type",
        type=click.Choice(["worker_collab", "direct_skill"], case_sensitive=False),
        show_choices=True,
    )
    billing_mode = click.prompt(
        "Billing mode",
        type=click.Choice(["pay_per_task", "subscription"], case_sensitive=False),
        show_choices=True,
    )

    rate_limit_per_day = None
    if billing_mode == "subscription":
        rate_limit_per_day = click.prompt(
            "rate_limit_per_day (required for subscription)",
            type=int,
            default=1000,
        )

    monetization = MonetizationConfig(
        function_type=function_type,
        billing_mode=billing_mode,
        rate_limit_per_day=rate_limit_per_day,
    )
    quadrant = monetization.quadrant_label()
    split = monetization.revenue_split()
    click.echo(
        click.style(
            f"  ✓ {quadrant}: {split['developer']:.0f}% Developer / "
            f"{split['worker']:.0f}% Worker / {split['platform']:.0f}% Platform",
            fg="cyan",
        )
    )
    click.echo()

    # ── 2. Basic fields ─────────────────────────────────────────────────
    skill_id = click.prompt("skill_id", type=str)
    version = click.prompt("version", default="1.0.0", show_default=True)
    developer_wallet = click.prompt("developer_wallet (EIP-55 0x... address)", type=str)
    price = click.prompt("price_per_task_usdc", type=float)
    entry_point = click.prompt("entry_point", default="main.py", show_default=True)
    gateway_url = click.prompt("gateway_url", type=str)

    click.echo()
    click.echo('output_schema — JSON object describing the return shape')
    schema_raw = click.prompt(
        "output_schema (JSON)",
        default='{"type": "object"}',
        show_default=False,
    )

    # ── 3. Build & validate ─────────────────────────────────────────────
    try:
        parsed_schema = json.loads(schema_raw)
    except json.JSONDecodeError as exc:
        click.echo(click.style(f"✖ Invalid JSON in output_schema: {exc}", fg="red"))
        sys.exit(1)

    raw: dict = {
        "skill_id": skill_id,
        "version": version,
        "developer_wallet": developer_wallet,
        "price_per_task_usdc": price,
        "monetization": {
            "function_type": function_type,
            "billing_mode": billing_mode,
            "rate_limit_per_day": rate_limit_per_day,
        },
        "entry_point": entry_point,
        "output_schema": parsed_schema,
        "gateway_url": gateway_url,
    }

    try:
        config = AIMSConfig.model_validate(raw)
    except Exception as exc:
        _print_validation_errors(exc)
        sys.exit(1)

    config.to_json_file(config_path)
    click.echo()
    click.echo(click.style(f"✔ aims.config.json written to {config_path}", fg="green", bold=True))


# ── login ───────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--private-key",
    required=True,
    prompt="Private key (hex)",
    hide_input=True,
    help="ECDSA private key in hex format (with or without 0x prefix).",
)
def login(private_key: str) -> None:
    """Encrypt and persist a developer private key to ``~/.aims/credentials``.

    The key is stored as an Ethereum keystore v3 JSON file, encrypted
    with a password you choose.
    """
    try:
        from eth_account import Account
        Account.from_key(private_key)
    except Exception as exc:
        click.echo(click.style(f"✖ Invalid private key: {exc}", fg="red"))
        sys.exit(1)

    password = click.prompt(
        "Encryption password",
        hide_input=True,
        confirmation_prompt=True,
    )

    try:
        from src.cli.credentials import store_private_key
        store_private_key(private_key, password)
    except OSError as exc:
        click.echo(click.style(f"✖ Failed to write credentials: {exc}", fg="red"))
        sys.exit(1)

    click.echo(click.style("✔ Private key encrypted and stored at ~/.aims/credentials", fg="green", bold=True))


# ── publish ─────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--gateway-url",
    default=None,
    help="Override the gateway URL from aims.config.json.",
)
@click.option(
    "--entry-point",
    default=None,
    help="Override the entry point (e.g. src/main.py).",
)
def publish(gateway_url: str | None, entry_point: str | None) -> None:
    """Full DRM pipeline: obfuscate, encrypt, sign, package, and register.

    Runs the complete 8-step publish workflow with a detailed ASCII
    audit table showing the 5% platform fee split.
    """
    from src.cli.publisher import publish_skill

    publish_skill(
        Path.cwd() / "aims.config.json",
        gateway_override=gateway_url,
        entry_point_override=entry_point,
    )


# ── CLI group ───────────────────────────────────────────────────────────────


@click.group()
def main() -> None:
    """AIMS Contributor CLI — tooling for skill developers."""


main.add_command(init)
main.add_command(login)
main.add_command(publish)


if __name__ == "__main__":
    main()
