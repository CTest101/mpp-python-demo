"""MPP Session HTTP Client — real 402 protocol flow.

Speaks the mppx session protocol:
  1. GET /resource → 402 + WWW-Authenticate: Payment intent="session"
  2. Open escrow channel on-chain (approve + open)
  3. GET /resource + Authorization: Payment {action: "open", tx, voucher}
  4. GET /resource + Authorization: Payment {action: "voucher", cumAmount, sig}
  5. Close: Authorization: Payment {action: "close", cumAmount, sig}

Compatible with mppx TypeScript server's `tempo.session()`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..core.config import TEMPO_CHAIN_ID
from ..core.escrow import EscrowClient, ESCROW_ADDRESS
from ..core.protocol import (
    PaymentChallenge,
    build_authorization_header,
    close_payload,
    open_payload,
    parse_challenge_from_response,
    parse_receipt,
    voucher_payload,
)
from ..core.voucher import SessionClient, compute_voucher_digest
from ..signer import Signer


@dataclass
class SessionHttpClient:
    """Python client that speaks the mppx session protocol over HTTP 402.

    Usage:
        signer = signer_from_env()
        async with SessionHttpClient(signer=signer, max_deposit=1_000_000) as client:
            # First fetch triggers: 402 → open channel → retry with open credential
            r1 = await client.fetch("http://localhost:5555/gallery")
            # Subsequent fetches: voucher credential only (~6ms)
            r2 = await client.fetch("http://localhost:5555/gallery")
            r3 = await client.fetch("http://localhost:5555/gallery")
            # Close the channel (on-chain settlement)
            receipt = await client.close("http://localhost:5555/gallery")
    """

    signer: Signer
    max_deposit: int = 1_000_000  # $1.00 in base units (6 decimals)
    rpc_url: str = ""

    # Internal state
    _http: httpx.AsyncClient = field(init=False, repr=False)
    _escrow: EscrowClient = field(init=False, repr=False)
    _session: SessionClient | None = field(init=False, default=None, repr=False)
    _channel_id: str = field(init=False, default="")
    _challenge: PaymentChallenge | None = field(init=False, default=None, repr=False)
    _source: str = field(init=False, default="")
    _salt: bytes = field(init=False, repr=False, default=b"")
    _request_count: int = field(init=False, default=0)
    _receipts: list[dict] = field(init=False, default_factory=list, repr=False)

    def __post_init__(self):
        from ..core.config import TEMPO_RPC, PATH_USD_ADDRESS

        rpc = self.rpc_url or TEMPO_RPC
        self._http = httpx.AsyncClient(timeout=60.0)
        self._escrow = EscrowClient(
            signer=self.signer,
            token_address=PATH_USD_ADDRESS,
            rpc_url=rpc,
        )
        self._salt = os.urandom(32)
        self._source = f"did:pkh:eip155:{TEMPO_CHAIN_ID}:{self.signer.address}"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._http.aclose()

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def cumulative_amount(self) -> int:
        return self._session.cumulative_amount if self._session else 0

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def receipts(self) -> list[dict]:
        return self._receipts

    async def fetch(self, url: str) -> httpx.Response:
        """Fetch a resource, automatically handling 402 session protocol.

        First call: GET → 402 → open channel → retry with open credential → 200
        Subsequent: GET with voucher credential → 200
        """
        if self._channel_id and self._challenge:
            # Channel already open — send voucher
            return await self._fetch_with_voucher(url)

        # First request — expect 402
        response = await self._http.get(url)

        if response.status_code != 402:
            return response

        challenge = parse_challenge_from_response(response)
        if not challenge or challenge.intent != "session":
            return response

        self._challenge = challenge

        # Open channel on-chain and retry with open credential
        return await self._open_and_retry(url, challenge)

    async def _open_and_retry(
        self, url: str, challenge: PaymentChallenge
    ) -> httpx.Response:
        """Sign open tx (don't broadcast — server will), then retry with open credential."""
        payee = challenge.recipient
        amount_per_request = int(challenge.amount)

        print(f"  ⛓️  Signing open tx (deposit ${self.max_deposit / 1e6:.2f})...")

        # Sign approve+open tx WITHOUT broadcasting — server broadcasts via fee payer
        raw_tx, channel_id = await self._escrow.sign_approve_and_open(
            payee=payee,
            deposit=self.max_deposit,
            salt=self._salt,
        )
        self._channel_id = channel_id
        print(f"  ✅ Channel: {channel_id[:18]}...")
        print(f"  📝 Signed TX: {raw_tx[:18]}... ({len(raw_tx)} chars)")

        # Initialize off-chain session
        self._session = SessionClient(
            signer=self.signer,
            channel_id=channel_id,
        )

        # Sign first voucher
        voucher = await self._session.sign_voucher(amount_per_request)

        # Build open credential — transaction is the RAW SIGNED TX, not tx hash!
        # The mppx server broadcasts it (possibly via fee payer)
        payload = open_payload(
            channel_id=channel_id,
            transaction=raw_tx,
            signature=voucher.signature,
            cumulative_amount=str(voucher.cumulative_amount),
        )
        auth = build_authorization_header(challenge, payload, self._source)

        # Retry with credential
        response = await self._http.get(url, headers={"Authorization": auth})
        self._request_count += 1
        self._collect_receipt(response)
        return response

    async def _fetch_with_voucher(self, url: str) -> httpx.Response:
        """Send request with a voucher credential."""
        assert self._session is not None
        assert self._challenge is not None

        amount_per_request = int(self._challenge.amount)
        voucher = await self._session.sign_voucher(amount_per_request)

        payload = voucher_payload(
            channel_id=self._channel_id,
            cumulative_amount=str(voucher.cumulative_amount),
            signature=voucher.signature,
        )
        auth = build_authorization_header(self._challenge, payload, self._source)

        response = await self._http.get(url, headers={"Authorization": auth})
        self._request_count += 1
        self._collect_receipt(response)
        return response

    async def close(self, url: str) -> dict | None:
        """Close the session — send close credential, server settles on-chain.

        Returns the close receipt from the server.
        """
        if not self._session or not self._challenge:
            return None

        # Sign a close voucher at current cumulative amount
        # (close doesn't increment — just re-signs the current amount)
        payload = close_payload(
            channel_id=self._channel_id,
            cumulative_amount=str(self._session.cumulative_amount),
            signature=(await self._sign_current_voucher()),
        )
        auth = build_authorization_header(self._challenge, payload, self._source)

        response = await self._http.get(url, headers={"Authorization": auth})
        receipt = parse_receipt(response.headers.get("payment-receipt", ""))

        if receipt:
            print(f"  ✅ Channel closed!")
            if receipt.get("txHash"):
                print(f"  📝 Settle TX: {receipt['txHash']}")
            print(f"  💰 Settled: {receipt.get('acceptedCumulative', '?')} base units")

        return receipt

    async def _sign_current_voucher(self) -> str:
        """Sign a voucher at the current cumulative amount (for close)."""
        assert self._session is not None
        digest = compute_voucher_digest(
            self._channel_id, self._session.cumulative_amount
        )
        sig_bytes = await self.signer.sign_hash(digest)
        return "0x" + sig_bytes.hex()

    def _collect_receipt(self, response: httpx.Response) -> None:
        """Collect receipt from response if present."""
        receipt_header = response.headers.get("payment-receipt", "")
        if receipt_header:
            receipt = parse_receipt(receipt_header)
            if receipt:
                self._receipts.append(receipt)
