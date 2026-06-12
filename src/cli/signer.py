"""EIP-191 signing for AIMS skill copyright provenance.

Constructs a structured message from the skill's identity and price,
then signs it with the developer's ECDSA private key (EIP-191 personal_sign).

Message format::

    AIMS-SKILL-AUTH:{skill_id}:{key_hash}:{price}
"""

from __future__ import annotations


def sign_skill(
    skill_id: str,
    key_hash: str,
    price: float,
    private_key_hex: str,
) -> dict:
    """Sign a skill provenance message using EIP-191.

    Returns:
        A dict with keys ``signature`` (hex string), ``message`` (the
        plaintext that was signed), and ``signer`` (checksummed address).
    """
    from eth_account import Account
    from eth_account.messages import encode_defunct

    message = f"AIMS-SKILL-AUTH:{skill_id}:{key_hash}:{price}"
    encoded = encode_defunct(primitive=message.encode())
    acct = Account.from_key(private_key_hex)
    signed = Account.sign_message(encoded, acct.key)

    return {
        "signature": signed.signature.hex(),
        "message": message,
        "signer": acct.address,
    }
