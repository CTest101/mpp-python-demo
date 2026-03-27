"""MPP Session — 简化版 Payment Channel (EIP-712 voucher 签名)。

完整 Session 需要链上 escrow 合约（TempoStreamChannel），这里实现协议层逻辑：
- Client: 签 EIP-712 累积 voucher
- Server: ecrecover 验证签名（微秒级，零链上调用）
- 链上结算在 close 时批量进行

EIP-712 domain/types 与合约一致：
  Domain: name="Tempo Stream Channel", version="1", verifyingContract=escrow
  Voucher: channelId(bytes32) + cumulativeAmount(uint128)
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data

from .config import TEMPO_CHAIN_ID


# ─── EIP-712 Domain & Types (matches contract) ──────────────────────────────

# Moderato testnet escrow contract
ESCROW_CONTRACT = "0xe1c4d3dce17bc111181ddf716f75bae49e61a336"

SESSION_DOMAIN = {
    "name": "Tempo Stream Channel",
    "version": "1",
    "chainId": TEMPO_CHAIN_ID,
    "verifyingContract": ESCROW_CONTRACT,
}

VOUCHER_TYPES = {
    "Voucher": [
        {"name": "channelId", "type": "bytes32"},
        {"name": "cumulativeAmount", "type": "uint128"},
    ],
}

EIP712_DOMAIN_TYPE = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]


def _build_voucher_typed_data(channel_id: str, cumulative_amount: int) -> dict:
    """Shared EIP-712 typed data construction — used by both sign and verify.

    Matches contract: Voucher(bytes32 channelId, uint128 cumulativeAmount)
    Domain: name="Tempo Stream Channel", version="1", verifyingContract=escrow
    """
    channel_bytes = bytes.fromhex(channel_id[2:] if channel_id.startswith("0x") else channel_id)
    return {
        "types": {**VOUCHER_TYPES, "EIP712Domain": EIP712_DOMAIN_TYPE},
        "primaryType": "Voucher",
        "domain": SESSION_DOMAIN,
        "message": {
            "channelId": channel_bytes,
            "cumulativeAmount": cumulative_amount,
        },
    }


# ─── Voucher ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Voucher:
    """一张累积 voucher — "我已消费 X"。"""
    channel_id: str           # bytes32 hex
    cumulative_amount: int    # 累积金额（base units, 6 decimals）
    nonce: int                # 递增 nonce (used for replay protection server-side, NOT in EIP-712)
    signature: str            # hex 签名
    signer: str               # 签名者地址


# ─── Client: Session Manager ────────────────────────────────────────────────

@dataclass
class SessionClient:
    """Client 端 session 管理 — 签累积 voucher（async）。"""

    signer: Any  # Signer ABC
    channel_id: str = field(default_factory=lambda: "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:32])
    cumulative_amount: int = 0
    nonce: int = 0

    async def sign_voucher(self, amount_delta: int) -> Voucher:
        """签一张新的累积 voucher。

        EIP-712 签名只包含 channelId + cumulativeAmount（与合约一致）。
        nonce 在应用层递增，用于 server 端 replay 保护。
        """
        self.cumulative_amount += amount_delta
        self.nonce += 1

        full_message = _build_voucher_typed_data(
            self.channel_id, self.cumulative_amount
        )
        signable = encode_typed_data(full_message=full_message)
        sig_bytes = await self.signer.sign_hash(signable.body)

        return Voucher(
            channel_id=self.channel_id,
            cumulative_amount=self.cumulative_amount,
            nonce=self.nonce,
            signature="0x" + sig_bytes.hex(),
            signer=self.signer.address,
        )


# ─── Server: Session Verifier ───────────────────────────────────────────────

@dataclass
class SessionChannel:
    """Server 端的一个 payment channel 状态。"""
    channel_id: str
    payer: str                # 预期的付款方地址
    deposit: int              # 存款额（base units）
    cumulative_verified: int = 0
    last_nonce: int = 0
    created_at: float = field(default_factory=time.time)
    # Track the best voucher signature for on-chain settlement
    best_signature: str = ""


class SessionVerifier:
    """Server 端 session 验证器 — ecrecover，零链上调用。"""

    def __init__(self):
        self._channels: dict[str, SessionChannel] = {}

    def open_channel(self, channel_id: str, payer: str, deposit: int) -> SessionChannel:
        """开通 payment channel。"""
        channel = SessionChannel(channel_id=channel_id, payer=payer, deposit=deposit)
        self._channels[channel_id] = channel
        return channel

    def top_up(self, channel_id: str, amount: int) -> SessionChannel | None:
        """追加存款（不中断 session）。"""
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

        # ⭐ ecrecover — EIP-712 without nonce (matches contract)
        full_message = _build_voucher_typed_data(
            voucher.channel_id, voucher.cumulative_amount
        )
        signable = encode_typed_data(full_message=full_message)
        sig_bytes = bytes.fromhex(voucher.signature[2:])

        try:
            recovered = Account._recover_hash(signable.body, signature=sig_bytes)
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
        """关闭 channel — 返回结算信息。"""
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
