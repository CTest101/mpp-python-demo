"""On-chain Session — full lifecycle with TempoStreamChannel escrow.

Client flow:  approve + open (on-chain) → sign vouchers (off-chain) → request close
Server flow:  verify vouchers (off-chain ecrecover) → close (on-chain, submit best voucher)

This bridges the off-chain session protocol (session.py) with the
on-chain escrow contract (onchain.py).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from .onchain import EscrowClient, ESCROW_ADDRESS
from .session import SessionClient, SessionVerifier, SessionChannel, Voucher
from .signer import Signer
from .config import TEMPO_RPC, PATH_USD_ADDRESS


# ─── On-chain Session Client ────────────────────────────────────────────────

@dataclass
class OnchainSessionClient:
    """Client: open channel on-chain → sign vouchers off-chain → request close.

    Usage:
        client = OnchainSessionClient(signer=signer, payee=server_address)
        channel_id, tx_hash = await client.open_channel(deposit=1_000_000)
        voucher = await client.sign_voucher(amount_delta=5000)
        # ... send voucher to server ...
        # server closes on-chain
    """
    signer: Signer
    payee: str  # server/payee address
    token_address: str = PATH_USD_ADDRESS
    rpc_url: str = TEMPO_RPC

    # Internal state
    _escrow: EscrowClient = field(init=False, repr=False)
    _session: SessionClient = field(init=False, repr=False)
    _channel_id: str = ""
    _salt: bytes = field(default_factory=lambda: os.urandom(32))

    def __post_init__(self):
        self._escrow = EscrowClient(
            signer=self.signer,
            token_address=self.token_address,
            rpc_url=self.rpc_url,
        )

    @property
    def channel_id(self) -> str:
        return self._channel_id

    async def open_channel(self, deposit: int) -> tuple[str, str]:
        """Open escrow channel on-chain (approve + open).

        Returns (channel_id, tx_hash).
        """
        tx_hash, channel_id = await self._escrow.approve_and_open(
            payee=self.payee,
            deposit=deposit,
            salt=self._salt,
        )
        self._channel_id = channel_id
        # Initialize off-chain session with the real channel ID
        self._session = SessionClient(
            signer=self.signer,
            channel_id=channel_id,
        )
        return channel_id, tx_hash

    async def sign_voucher(self, amount_delta: int) -> Voucher:
        """Sign a cumulative voucher (off-chain, EIP-712)."""
        if not self._channel_id:
            raise RuntimeError("Channel not opened yet. Call open_channel() first.")
        return await self._session.sign_voucher(amount_delta)

    @property
    def cumulative_amount(self) -> int:
        return self._session.cumulative_amount if hasattr(self, '_session') else 0


# ─── On-chain Session Server ────────────────────────────────────────────────

@dataclass
class OnchainSessionServer:
    """Server: verify vouchers off-chain → close on-chain.

    The server (payee) collects vouchers, verifies them via ecrecover,
    and when ready, submits the highest voucher to the escrow contract
    to claim funds.
    """
    signer: Signer  # Server's signer (payee)
    rpc_url: str = TEMPO_RPC

    _verifier: SessionVerifier = field(init=False, repr=False)
    _escrow: EscrowClient = field(init=False, repr=False)

    def __post_init__(self):
        self._verifier = SessionVerifier()
        self._escrow = EscrowClient(
            signer=self.signer,
            rpc_url=self.rpc_url,
        )

    def open_channel(self, channel_id: str, payer: str, deposit: int) -> SessionChannel:
        """Register a channel opened by the client."""
        return self._verifier.open_channel(channel_id, payer, deposit)

    def verify_voucher(self, voucher: Voucher) -> tuple[bool, int, str]:
        """Verify a voucher off-chain (ecrecover)."""
        return self._verifier.verify_voucher(voucher)

    def get_channel(self, channel_id: str) -> SessionChannel | None:
        return self._verifier.get_channel(channel_id)

    async def close_channel(self, channel_id: str) -> dict:
        """Close channel on-chain — submit the best voucher to escrow.

        Returns settlement info + tx hash.
        """
        channel = self._verifier.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel not found: {channel_id}")

        cumulative = channel.cumulative_verified
        signature = bytes.fromhex(
            channel.best_signature[2:]
            if channel.best_signature.startswith("0x")
            else channel.best_signature
        )

        # Submit to escrow contract
        tx_hash = await self._escrow.close(channel_id, cumulative, signature)

        # Remove from verifier
        result = self._verifier.close_channel(channel_id) or {}
        result["tx_hash"] = tx_hash
        return result
