"""Server-side session verification — ecrecover, zero on-chain calls."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from eth_account import Account

from ..core.voucher import Voucher, compute_voucher_digest


@dataclass
class SessionChannel:
    """Server 端 payment channel 状态。"""
    channel_id: str
    payer: str
    deposit: int
    cumulative_verified: int = 0
    last_nonce: int = 0
    best_signature: str = ""  # highest verified voucher sig (for on-chain settlement)
    created_at: float = field(default_factory=time.time)


class SessionVerifier:
    """Server 端 session 验证器 — ecrecover，零链上调用。"""

    def __init__(self):
        self._channels: dict[str, SessionChannel] = {}

    def open_channel(self, channel_id: str, payer: str, deposit: int) -> SessionChannel:
        channel = SessionChannel(channel_id=channel_id, payer=payer, deposit=deposit)
        self._channels[channel_id] = channel
        return channel

    def top_up(self, channel_id: str, amount: int) -> SessionChannel | None:
        channel = self._channels.get(channel_id)
        if not channel:
            return None
        channel.deposit += amount
        return channel

    def verify_voucher(self, voucher: Voucher) -> tuple[bool, int, str]:
        """验证 voucher，返回 (success, delta, error_msg)。"""
        channel = self._channels.get(voucher.channel_id)
        if not channel:
            return False, 0, "channel_not_found"

        if voucher.nonce <= channel.last_nonce:
            return False, 0, "nonce_not_incremented"

        if voucher.cumulative_amount <= channel.cumulative_verified:
            return False, 0, "amount_not_incremented"

        if voucher.cumulative_amount > channel.deposit:
            return False, 0, "exceeds_deposit"

        # Compute digest and recover signer
        digest = compute_voucher_digest(voucher.channel_id, voucher.cumulative_amount)
        sig_bytes = bytes.fromhex(voucher.signature[2:])

        try:
            recovered = Account._recover_hash(digest, signature=sig_bytes)
        except Exception:
            return False, 0, "invalid_signature"

        if recovered.lower() != channel.payer.lower():
            return False, 0, f"signer_mismatch: expected {channel.payer}, got {recovered}"

        delta = voucher.cumulative_amount - channel.cumulative_verified
        channel.cumulative_verified = voucher.cumulative_amount
        channel.last_nonce = voucher.nonce
        channel.best_signature = voucher.signature
        return True, delta, ""

    def close_channel(self, channel_id: str) -> dict | None:
        channel = self._channels.pop(channel_id, None)
        if not channel:
            return None
        return {
            "channel_id": channel_id,
            "total_spent": channel.cumulative_verified,
            "refund": channel.deposit - channel.cumulative_verified,
            "payer": channel.payer,
            "best_signature": channel.best_signature,
        }

    def get_channel(self, channel_id: str) -> SessionChannel | None:
        return self._channels.get(channel_id)
