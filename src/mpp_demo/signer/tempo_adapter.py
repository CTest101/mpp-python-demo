"""TempoMethod adapter — 让 Signer 接管 pympp 的签名流程。

核心思路：
1. 继承 TempoMethod，override `_build_tempo_transfer`
2. 用 `tx.get_signing_hash()` 拿到 32-byte hash
3. 用我们的 Signer.sign_hash() 签名
4. 手动拼装 signed tx（bypass `tx.sign(private_key)`）

这样 KMS/MPC/Passkey 等远程 signer 就能直接接入。
"""

from __future__ import annotations

import time
from typing import Optional

import attrs
from mpp.methods.tempo.client import (
    TempoMethod,
    DEFAULT_GAS_LIMIT,
    EXPIRING_NONCE_KEY,
    FEE_PAYER_VALID_BEFORE_SECS,
)
from mpp.methods.tempo._rpc import estimate_gas, get_tx_params
from mpp.methods.tempo._attribution import encode as encode_attribution
from mpp.methods.tempo._defaults import CHAIN_RPC_URLS
from mpp import Challenge, Credential
from pytempo import Call, TempoTransaction
from pytempo.models import Signature, as_address

from .base import Signer


class SignerTempoMethod(TempoMethod):
    """TempoMethod that delegates signing to an abstract Signer.

    Instead of calling `tx.sign(private_key)`, we:
    1. Build the unsigned TempoTransaction
    2. Call `tx.get_signing_hash()` to get the 32-byte digest
    3. Call `signer.sign_hash(hash)` to sign externally
    4. Manually attach the Signature to the tx

    This allows KMS, MPC, hardware wallets, and passkeys to sign
    Tempo transactions without exposing private keys.
    """

    def __init__(self, signer: Signer, intents: dict | None = None, **kwargs):
        # 用 signer.address 作为 account 的替代
        self._signer = signer
        super().__init__(**kwargs)
        if intents:
            self._intents = dict(intents)

    async def create_credential(self, challenge: Challenge) -> Credential:
        """Override to use our Signer instead of TempoAccount."""
        if challenge.intent != "charge":
            raise ValueError(f"Unsupported intent: {challenge.intent}")

        request = challenge.request
        method_details = request.get("methodDetails", {})
        use_fee_payer = (
            method_details.get("feePayer", False) if isinstance(method_details, dict) else False
        )

        nonce_key = request.get("nonce_key", 0)
        if isinstance(nonce_key, str):
            nonce_key = int(nonce_key, 16) if nonce_key.startswith("0x") else int(nonce_key)

        memo = method_details.get("memo") if isinstance(method_details, dict) else None
        if memo is None:
            memo = encode_attribution(server_id=challenge.realm, client_id=self.client_id)

        # Resolve RPC URL
        rpc_url = self.rpc_url
        expected_chain_id: int | None = None
        challenge_chain_id = (
            method_details.get("chainId") if isinstance(method_details, dict) else None
        )
        if challenge_chain_id is not None:
            try:
                parsed = int(challenge_chain_id)
                resolved = CHAIN_RPC_URLS.get(parsed)
                if resolved:
                    rpc_url = resolved
                    expected_chain_id = parsed
            except (TypeError, ValueError):
                pass

        if expected_chain_id is None and self.chain_id is not None:
            expected_chain_id = self.chain_id

        # 用 Signer 签名构造交易
        raw_tx, chain_id = await self._build_with_signer(
            amount=request["amount"],
            currency=request["currency"],
            recipient=request["recipient"],
            nonce_key=nonce_key,
            memo=memo,
            rpc_url=rpc_url,
            expected_chain_id=expected_chain_id,
            awaiting_fee_payer=use_fee_payer,
        )

        return Credential(
            challenge=challenge.to_echo(),
            payload={"type": "transaction", "signature": raw_tx},
            source=f"did:pkh:eip155:{chain_id}:{self._signer.address}",
        )

    async def _build_with_signer(
        self,
        amount: str,
        currency: str,
        recipient: str,
        nonce_key: int = 0,
        memo: str | None = None,
        rpc_url: str | None = None,
        expected_chain_id: int | None = None,
        awaiting_fee_payer: bool = False,
    ) -> tuple[str, int]:
        """Build a TempoTransaction and sign with our Signer."""
        resolved_rpc = rpc_url or self.rpc_url

        if memo:
            transfer_data = self._encode_transfer_with_memo(recipient, int(amount), memo)
        else:
            transfer_data = self._encode_transfer(recipient, int(amount))

        chain_id, on_chain_nonce, gas_price = await get_tx_params(
            resolved_rpc, self._signer.address
        )

        if expected_chain_id is not None and chain_id != expected_chain_id:
            from mpp.methods.tempo.client import TransactionError
            raise TransactionError(
                f"Chain ID mismatch: RPC returned {chain_id}, expected {expected_chain_id}"
            )

        if awaiting_fee_payer:
            resolved_nonce_key = EXPIRING_NONCE_KEY
            resolved_nonce = 0
            valid_before = int(time.time()) + FEE_PAYER_VALID_BEFORE_SECS
        else:
            resolved_nonce_key = nonce_key
            resolved_nonce = on_chain_nonce
            valid_before = None

        gas_limit = DEFAULT_GAS_LIMIT
        try:
            estimated = await estimate_gas(
                resolved_rpc, self._signer.address, currency, transfer_data
            )
            gas_limit = max(gas_limit, estimated + 5_000)
        except Exception:
            pass

        # 1. 构造未签名交易
        tx = TempoTransaction.create(
            chain_id=chain_id,
            gas_limit=gas_limit,
            max_fee_per_gas=gas_price,
            max_priority_fee_per_gas=gas_price,
            nonce=resolved_nonce,
            nonce_key=resolved_nonce_key,
            fee_token=None if awaiting_fee_payer else currency,
            awaiting_fee_payer=awaiting_fee_payer,
            valid_before=valid_before,
            calls=(Call.create(to=currency, value=0, data=transfer_data),),
        )

        # 2. 获取 signing hash（32 bytes）
        signing_hash = tx.get_signing_hash(for_fee_payer=False)

        # 3. 用 Signer 签名 ⭐ 关键一步 — 这里可以是 KMS/MPC/硬件钱包
        sig_bytes = await self._signer.sign_hash(signing_hash)

        # 4. 解析签名并附加到交易
        sig = Signature.from_bytes(sig_bytes)
        sender_addr = as_address(self._signer.address)
        signed_tx = attrs.evolve(tx, sender_signature=sig, sender_address=sender_addr)

        if awaiting_fee_payer:
            from mpp.methods.tempo.fee_payer_envelope import encode_fee_payer_envelope
            return "0x" + encode_fee_payer_envelope(signed_tx).hex(), chain_id

        return "0x" + signed_tx.encode().hex(), chain_id
