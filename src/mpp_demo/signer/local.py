"""LocalSigner — signs with a local private key via eth-account.

Suitable for development, testing, and server-side automated wallets.
"""

from eth_account import Account
from mpp.methods.tempo import TempoAccount

from .base import Signer


class LocalSigner(Signer):
    """Sign with an in-memory private key."""

    def __init__(self, private_key: str) -> None:
        """Initialize with a hex private key (with or without 0x prefix)."""
        self._account = Account.from_key(private_key)
        self._private_key = private_key

    @property
    def address(self) -> str:
        return self._account.address

    async def sign_hash(self, msg_hash: bytes) -> bytes:
        """Sign a 32-byte hash without EIP-191 prefix.

        Sync under the hood (CPU-bound), but async interface
        for compatibility with remote signers.
        """
        if len(msg_hash) != 32:
            raise ValueError(f"msg_hash must be 32 bytes, got {len(msg_hash)}")
        signed = self._account.unsafe_sign_hash(msg_hash)
        return signed.r.to_bytes(32, "big") + signed.s.to_bytes(32, "big") + bytes([signed.v])

    def to_tempo_account(self) -> TempoAccount:
        """Bridge to pympp TempoAccount."""
        return TempoAccount.from_key(self._private_key)
