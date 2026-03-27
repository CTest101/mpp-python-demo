"""Abstract Signer — the extension point for all signing backends.

Implement this to add:
- KMS signers (AWS KMS, GCP Cloud KMS)
- MPC signers (Cobo TSS, Fireblocks)
- Hardware wallets (Ledger, Trezor)
- Passkey / WebAuthn signers
"""

from abc import ABC, abstractmethod


class Signer(ABC):
    """Abstract base class for all signers.

    A Signer knows how to:
    1. Expose its address
    2. Sign a 32-byte hash (no prefix, for EIP-712 etc.)
    3. Bridge to pympp's TempoAccount

    sign_hash is async to support remote signers (KMS, MPC, etc.).
    """

    @property
    @abstractmethod
    def address(self) -> str:
        """Checksummed Ethereum address."""
        ...

    @abstractmethod
    async def sign_hash(self, msg_hash: bytes) -> bytes:
        """Sign a 32-byte hash. Returns 65-byte signature (r || s || v).

        This is the core primitive. EIP-712 typed data hashing happens
        upstream; the signer only sees the final 32-byte digest.

        Async to support remote signers (KMS API call, MPC ceremony, etc.).
        """
        ...

    def to_tempo_account(self):
        """Bridge to pympp TempoAccount for SDK integration.

        Default: creates TempoAccount from private key (only works for LocalSigner).
        Override this in remote signers (KMS/MPC) to return a custom adapter.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support direct TempoAccount conversion. "
            f"Override to_tempo_account() for remote signer integration."
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.address[:10]}...>"
