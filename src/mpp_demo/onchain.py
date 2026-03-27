"""On-chain escrow interaction — TempoStreamChannel contract client.

Handles:
- TIP-20 approve + escrow.open (payer deposits)
- escrow.settle / close (payee claims)
- escrow.topUp (payer adds funds)
- Read-only: computeChannelId, getVoucherDigest, getChannel

All transactions use pytempo TempoTransaction + Signer.sign_hash().
RPC calls via httpx (eth_sendRawTransaction, eth_call, etc.).
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import attrs
import httpx
from eth_abi import encode, decode
from eth_utils import function_signature_to_4byte_selector
from pytempo import Call, TempoTransaction
from pytempo.models import Signature, as_address
from pytempo.contracts.tip20 import TIP20

from .config import TEMPO_CHAIN_ID, TEMPO_RPC, PATH_USD_ADDRESS
from .signer import Signer

# ─── Contract Addresses ─────────────────────────────────────────────────────

ESCROW_ADDRESS = "0xe1c4d3dce17bc111181ddf716f75bae49e61a336"

# ─── ABI Function Selectors ─────────────────────────────────────────────────

_SEL_OPEN = function_signature_to_4byte_selector(
    "open(address,address,uint128,bytes32,address)"
)
_SEL_SETTLE = function_signature_to_4byte_selector(
    "settle(bytes32,uint128,bytes)"
)
_SEL_CLOSE = function_signature_to_4byte_selector(
    "close(bytes32,uint128,bytes)"
)
_SEL_TOPUP = function_signature_to_4byte_selector(
    "topUp(bytes32,uint256)"
)
_SEL_COMPUTE_CHANNEL_ID = function_signature_to_4byte_selector(
    "computeChannelId(address,address,address,bytes32,address)"
)
_SEL_GET_VOUCHER_DIGEST = function_signature_to_4byte_selector(
    "getVoucherDigest(bytes32,uint128)"
)

# ─── Default config ──────────────────────────────────────────────────────────

DEFAULT_GAS_LIMIT = 1_000_000
RPC_TIMEOUT = 30.0


# ─── Low-level RPC helpers ───────────────────────────────────────────────────

async def _rpc_call(
    rpc_url: str,
    method: str,
    params: list[Any],
    *,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """JSON-RPC call."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if client is not None:
        resp = await client.post(rpc_url, json=payload)
    else:
        async with httpx.AsyncClient(timeout=RPC_TIMEOUT) as c:
            resp = await c.post(rpc_url, json=payload)
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise RuntimeError(f"RPC error: {result['error']}")
    return result["result"]


async def _get_tx_params(rpc_url: str, sender: str) -> tuple[int, int, int]:
    """Fetch (chain_id, nonce, gas_price) concurrently."""
    chain_hex, nonce_hex, gas_hex = await asyncio.gather(
        _rpc_call(rpc_url, "eth_chainId", []),
        _rpc_call(rpc_url, "eth_getTransactionCount", [sender, "pending"]),
        _rpc_call(rpc_url, "eth_gasPrice", []),
    )
    return int(chain_hex, 16), int(nonce_hex, 16), int(gas_hex, 16)


async def _send_tx(rpc_url: str, raw_tx_hex: str) -> str:
    """Send signed transaction, return tx hash."""
    return await _rpc_call(rpc_url, "eth_sendRawTransaction", [raw_tx_hex])


async def _eth_call(rpc_url: str, to: str, data: str) -> str:
    """eth_call (read-only)."""
    return await _rpc_call(rpc_url, "eth_call", [{"to": to, "data": data}, "latest"])


async def _wait_for_receipt(
    rpc_url: str, tx_hash: str, *, timeout: float = 60.0, poll_interval: float = 2.0
) -> dict:
    """Poll for transaction receipt."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await _rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        if result is not None:
            status = int(result.get("status", "0x0"), 16)
            if status != 1:
                raise RuntimeError(f"Transaction reverted: {tx_hash}")
            return result
        await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Receipt not found after {timeout}s for {tx_hash}")


# ─── Calldata Encoding ──────────────────────────────────────────────────────

def _encode_open(
    payee: str, token: str, deposit: int, salt: bytes, authorized_signer: str
) -> str:
    """Encode escrow.open(address,address,uint128,bytes32,address)."""
    args = encode(
        ["address", "address", "uint128", "bytes32", "address"],
        [payee, token, deposit, salt, authorized_signer],
    )
    return "0x" + _SEL_OPEN.hex() + args.hex()


def _encode_settle(channel_id: bytes, cumulative_amount: int, signature: bytes) -> str:
    """Encode escrow.settle(bytes32,uint128,bytes)."""
    args = encode(
        ["bytes32", "uint128", "bytes"],
        [channel_id, cumulative_amount, signature],
    )
    return "0x" + _SEL_SETTLE.hex() + args.hex()


def _encode_close(channel_id: bytes, cumulative_amount: int, signature: bytes) -> str:
    """Encode escrow.close(bytes32,uint128,bytes)."""
    args = encode(
        ["bytes32", "uint128", "bytes"],
        [channel_id, cumulative_amount, signature],
    )
    return "0x" + _SEL_CLOSE.hex() + args.hex()


def _encode_topup(channel_id: bytes, additional_deposit: int) -> str:
    """Encode escrow.topUp(bytes32,uint256)."""
    args = encode(["bytes32", "uint256"], [channel_id, additional_deposit])
    return "0x" + _SEL_TOPUP.hex() + args.hex()


def _encode_compute_channel_id(
    payer: str, payee: str, token: str, salt: bytes, authorized_signer: str
) -> str:
    """Encode escrow.computeChannelId view call."""
    args = encode(
        ["address", "address", "address", "bytes32", "address"],
        [payer, payee, token, salt, authorized_signer],
    )
    return "0x" + _SEL_COMPUTE_CHANNEL_ID.hex() + args.hex()


def _encode_get_voucher_digest(channel_id: bytes, cumulative_amount: int) -> str:
    """Encode escrow.getVoucherDigest view call."""
    args = encode(["bytes32", "uint128"], [channel_id, cumulative_amount])
    return "0x" + _SEL_GET_VOUCHER_DIGEST.hex() + args.hex()


# ─── Transaction Builder ────────────────────────────────────────────────────

async def _build_and_send_tx(
    signer: Signer,
    calls: list[Call],
    rpc_url: str = TEMPO_RPC,
    *,
    wait_receipt: bool = True,
) -> str:
    """Build a TempoTransaction with given calls, sign it, send it, optionally wait for receipt.

    Returns tx hash.
    """
    chain_id, nonce, gas_price = await _get_tx_params(rpc_url, signer.address)

    tx = TempoTransaction.create(
        chain_id=chain_id,
        gas_limit=DEFAULT_GAS_LIMIT * len(calls),  # scale gas with number of calls
        max_fee_per_gas=gas_price,
        max_priority_fee_per_gas=gas_price,
        nonce=nonce,
        nonce_key=0,
        fee_token=PATH_USD_ADDRESS,  # pay gas in pathUSD
        calls=tuple(calls),
    )

    signing_hash = tx.get_signing_hash(for_fee_payer=False)
    sig_bytes = await signer.sign_hash(signing_hash)
    sig = Signature.from_bytes(sig_bytes)
    sender_addr = as_address(signer.address)
    signed_tx = attrs.evolve(tx, sender_signature=sig, sender_address=sender_addr)

    raw_hex = "0x" + signed_tx.encode().hex()
    tx_hash = await _send_tx(rpc_url, raw_hex)

    if wait_receipt:
        await _wait_for_receipt(rpc_url, tx_hash)

    return tx_hash


# ─── EscrowClient ───────────────────────────────────────────────────────────

@dataclass
class EscrowClient:
    """Client for TempoStreamChannel escrow contract.

    Wraps open/settle/close/topUp + read-only helpers.
    """
    signer: Signer
    escrow_address: str = ESCROW_ADDRESS
    token_address: str = PATH_USD_ADDRESS
    rpc_url: str = TEMPO_RPC

    # ── Write operations ──────────────────────────────────────────────────

    async def approve_and_open(
        self,
        payee: str,
        deposit: int,
        salt: bytes,
        authorized_signer: str = "0x0000000000000000000000000000000000000000",
    ) -> tuple[str, str]:
        """Approve pathUSD + open escrow channel in a single Tempo tx (batched calls).

        Returns (tx_hash, channel_id_hex).
        """
        # Build approve call via TIP20 helper
        tip20 = TIP20(self.token_address)
        approve_call = tip20.approve(spender=self.escrow_address, amount=deposit)

        # Build open call
        open_data = _encode_open(payee, self.token_address, deposit, salt, authorized_signer)
        open_call = Call.create(to=self.escrow_address, value=0, data=open_data)

        # Send both in one transaction
        tx_hash = await _build_and_send_tx(
            self.signer, [approve_call, open_call], self.rpc_url
        )

        # Compute channel ID off-chain
        channel_id = await self.compute_channel_id(
            self.signer.address, payee, salt, authorized_signer
        )

        return tx_hash, channel_id

    async def settle(
        self, channel_id: str, cumulative_amount: int, signature: bytes
    ) -> str:
        """Submit voucher to claim partial funds. Returns tx hash."""
        channel_bytes = bytes.fromhex(
            channel_id[2:] if channel_id.startswith("0x") else channel_id
        )
        data = _encode_settle(channel_bytes, cumulative_amount, signature)
        call = Call.create(to=self.escrow_address, value=0, data=data)
        return await _build_and_send_tx(self.signer, [call], self.rpc_url)

    async def close(
        self, channel_id: str, cumulative_amount: int, signature: bytes
    ) -> str:
        """Close channel with final voucher. Returns tx hash."""
        channel_bytes = bytes.fromhex(
            channel_id[2:] if channel_id.startswith("0x") else channel_id
        )
        data = _encode_close(channel_bytes, cumulative_amount, signature)
        call = Call.create(to=self.escrow_address, value=0, data=data)
        return await _build_and_send_tx(self.signer, [call], self.rpc_url)

    async def top_up(self, channel_id: str, additional_deposit: int) -> str:
        """Add more funds to channel. Returns tx hash."""
        channel_bytes = bytes.fromhex(
            channel_id[2:] if channel_id.startswith("0x") else channel_id
        )
        # Approve additional amount first
        tip20 = TIP20(self.token_address)
        approve_call = tip20.approve(
            spender=self.escrow_address, amount=additional_deposit
        )
        topup_data = _encode_topup(channel_bytes, additional_deposit)
        topup_call = Call.create(to=self.escrow_address, value=0, data=topup_data)
        return await _build_and_send_tx(
            self.signer, [approve_call, topup_call], self.rpc_url
        )

    # ── Read-only operations ──────────────────────────────────────────────

    async def compute_channel_id(
        self,
        payer: str,
        payee: str,
        salt: bytes,
        authorized_signer: str = "0x0000000000000000000000000000000000000000",
    ) -> str:
        """Compute channel ID without sending a tx."""
        data = _encode_compute_channel_id(
            payer, payee, self.token_address, salt, authorized_signer
        )
        result = await _eth_call(self.rpc_url, self.escrow_address, data)
        return result  # bytes32 hex

    async def get_voucher_digest(
        self, channel_id: str, cumulative_amount: int
    ) -> bytes:
        """Get the EIP-712 digest for a voucher (for signing)."""
        channel_bytes = bytes.fromhex(
            channel_id[2:] if channel_id.startswith("0x") else channel_id
        )
        data = _encode_get_voucher_digest(channel_bytes, cumulative_amount)
        result = await _eth_call(self.rpc_url, self.escrow_address, data)
        return bytes.fromhex(result[2:] if result.startswith("0x") else result)
