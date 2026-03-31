"""MPP Session — Payment Channel (EIP-712 voucher 签名)。

EIP-712 domain/types 与 TempoStreamChannel 合约完全一致：
  Domain: name="Tempo Stream Channel", version="1", verifyingContract=escrow
  Voucher: channelId(bytes32) + cumulativeAmount(uint128)
  digest = keccak256(0x1901 || domainSeparator || structHash)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from eth_abi import encode as abi_encode
from eth_utils import keccak

from .config import TEMPO_CHAIN_ID


# ─── EIP-712 (matches TempoStreamChannel contract exactly) ──────────────────

ESCROW_CONTRACT = "0xe1c4d3dce17bc111181ddf716f75bae49e61a336"

VOUCHER_TYPEHASH = keccak(b"Voucher(bytes32 channelId,uint128 cumulativeAmount)")

_DOMAIN_TYPE_HASH = keccak(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
_NAME_HASH = keccak(b"Tempo Stream Channel")
_VERSION_HASH = keccak(b"1")

DOMAIN_SEPARATOR = keccak(abi_encode(
    ["bytes32", "bytes32", "bytes32", "uint256", "address"],
    [_DOMAIN_TYPE_HASH, _NAME_HASH, _VERSION_HASH, TEMPO_CHAIN_ID, ESCROW_CONTRACT],
))

SESSION_DOMAIN = {
    "name": "Tempo Stream Channel",
    "version": "1",
    "chainId": TEMPO_CHAIN_ID,
    "verifyingContract": ESCROW_CONTRACT,
}


def compute_voucher_digest(channel_id: str, cumulative_amount: int) -> bytes:
    """Compute EIP-712 digest — matches contract's getVoucherDigest() exactly.

    digest = keccak256(0x1901 || domainSeparator || structHash)
    structHash = keccak256(abi.encode(VOUCHER_TYPEHASH, channelId, cumulativeAmount))
    """
    channel_bytes = bytes.fromhex(channel_id[2:] if channel_id.startswith("0x") else channel_id)
    struct_hash = keccak(abi_encode(
        ["bytes32", "bytes32", "uint128"],
        [VOUCHER_TYPEHASH, channel_bytes, cumulative_amount],
    ))
    return keccak(b"\x19\x01" + DOMAIN_SEPARATOR + struct_hash)


def _build_voucher_typed_data(channel_id: str, cumulative_amount: int) -> dict:
    """Typed data representation (for display/documentation)."""
    return {
        "types": {
            "Voucher": [
                {"name": "channelId", "type": "bytes32"},
                {"name": "cumulativeAmount", "type": "uint128"},
            ],
        },
        "primaryType": "Voucher",
        "domain": SESSION_DOMAIN,
        "message": {
            "channelId": channel_id,
            "cumulativeAmount": cumulative_amount,
        },
    }


# ─── Voucher ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Voucher:
    """一张累积 voucher — "我已消费 X"。"""
    channel_id: str           # bytes32 hex
    cumulative_amount: int    # 累积金额（base units, 6 decimals）
    nonce: int                # app-level replay protection (NOT in EIP-712)
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
        """签一张新的累积 voucher。"""
        self.cumulative_amount += amount_delta
        self.nonce += 1

        # Compute digest matching contract exactly
        digest = compute_voucher_digest(self.channel_id, self.cumulative_amount)
        sig_bytes = await self.signer.sign_hash(digest)

        return Voucher(
            channel_id=self.channel_id,
            cumulative_amount=self.cumulative_amount,
            nonce=self.nonce,
            signature="0x" + sig_bytes.hex(),
            signer=self.signer.address,
        )
