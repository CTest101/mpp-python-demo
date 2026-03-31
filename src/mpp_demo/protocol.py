"""MPP Protocol — Challenge parsing and Credential building.

Implements the Payment Authentication Scheme (RFC draft) for Python clients.
Compatible with mppx TypeScript SDK's Challenge/Credential format.

WWW-Authenticate: Payment id="...", realm="...", method="tempo", intent="session",
    request="<base64url>", expires="...", description="..."

Authorization: Payment <base64url(JSON credential)>
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any


# ─── Challenge Parsing ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaymentChallenge:
    """Parsed Payment challenge from WWW-Authenticate header."""

    id: str
    realm: str
    method: str           # "tempo"
    intent: str           # "charge" or "session"
    request: dict         # decoded request body
    request_b64: str      # original base64url-encoded request
    expires: str = ""
    description: str = ""

    @property
    def amount(self) -> str:
        return self.request.get("amount", "0")

    @property
    def currency(self) -> str:
        return self.request.get("currency", "")

    @property
    def recipient(self) -> str:
        return self.request.get("recipient", "")

    @property
    def chain_id(self) -> int | None:
        md = self.request.get("methodDetails", {})
        return md.get("chainId")

    @property
    def escrow_contract(self) -> str | None:
        md = self.request.get("methodDetails", {})
        return md.get("escrowContract")

    @property
    def fee_payer(self) -> bool:
        md = self.request.get("methodDetails", {})
        return md.get("feePayer", False)

    @property
    def unit_type(self) -> str:
        return self.request.get("unitType", "")


def _b64url_decode(s: str) -> bytes:
    """Decode base64url (no padding)."""
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _b64url_encode(data: bytes) -> str:
    """Encode to base64url (no padding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _parse_auth_params(header: str) -> dict[str, str]:
    """Parse auth-param pairs from WWW-Authenticate header.

    Handles: Payment key="value", key="value", ...
    Values may contain base64url chars (no quotes inside values expected).
    """
    # Strip "Payment " prefix
    if header.lower().startswith("payment "):
        header = header[8:]

    params = {}
    # Match key="value" pairs (value can contain any non-quote chars)
    for match in re.finditer(r'(\w+)="([^"]*)"', header):
        params[match.group(1)] = match.group(2)
    return params


def parse_challenge(www_authenticate: str) -> PaymentChallenge:
    """Parse a WWW-Authenticate: Payment header into a PaymentChallenge."""
    params = _parse_auth_params(www_authenticate)

    request_b64 = params.get("request", "")
    try:
        request_data = json.loads(_b64url_decode(request_b64))
    except Exception:
        request_data = {}

    return PaymentChallenge(
        id=params.get("id", ""),
        realm=params.get("realm", ""),
        method=params.get("method", ""),
        intent=params.get("intent", ""),
        request=request_data,
        request_b64=request_b64,
        expires=params.get("expires", ""),
        description=params.get("description", ""),
    )


def parse_challenge_from_response(response) -> PaymentChallenge | None:
    """Extract and parse Payment challenge from an HTTP response."""
    www_auth = response.headers.get("www-authenticate", "")
    if not www_auth or not www_auth.lower().startswith("payment "):
        return None
    return parse_challenge(www_auth)


# ─── Credential Building ────────────────────────────────────────────────────


@dataclass
class ChallengeEcho:
    """Echo the challenge back in the credential (server uses HMAC to verify)."""
    id: str
    realm: str
    method: str
    intent: str
    request: str  # base64url-encoded request (as-is from challenge)


def _build_credential_json(
    challenge: PaymentChallenge,
    payload: dict[str, Any],
    source: str,
) -> str:
    """Build a credential JSON string.

    The challenge echo must include ALL fields from the original challenge
    (id, realm, method, intent, request, expires, description) because
    the server recomputes the HMAC from these fields to verify the challenge
    was issued by this server.
    """
    echo: dict[str, Any] = {
        "id": challenge.id,
        "realm": challenge.realm,
        "method": challenge.method,
        "intent": challenge.intent,
        "request": challenge.request_b64,
    }
    # Include optional fields that are part of the HMAC computation
    if challenge.expires:
        echo["expires"] = challenge.expires
    if challenge.description:
        echo["description"] = challenge.description

    credential = {
        "challenge": echo,
        "payload": payload,
        "source": source,
    }
    return json.dumps(credential, separators=(",", ":"))


def build_authorization_header(
    challenge: PaymentChallenge,
    payload: dict[str, Any],
    source: str,
) -> str:
    """Build Authorization: Payment <credential> header value."""
    cred_json = _build_credential_json(challenge, payload, source)
    encoded = _b64url_encode(cred_json.encode("utf-8"))
    return f"Payment {encoded}"


# ─── Session Credential Payloads (match mppx Types.ts) ─────────────────────


def open_payload(
    channel_id: str,
    transaction: str,
    signature: str,
    cumulative_amount: str,
    authorized_signer: str | None = None,
) -> dict[str, Any]:
    """Build an 'open' credential payload."""
    p: dict[str, Any] = {
        "action": "open",
        "type": "transaction",
        "channelId": channel_id,
        "transaction": transaction,
        "signature": signature,
        "cumulativeAmount": cumulative_amount,
    }
    if authorized_signer:
        p["authorizedSigner"] = authorized_signer
    return p


def voucher_payload(
    channel_id: str,
    cumulative_amount: str,
    signature: str,
) -> dict[str, Any]:
    """Build a 'voucher' credential payload."""
    return {
        "action": "voucher",
        "channelId": channel_id,
        "cumulativeAmount": cumulative_amount,
        "signature": signature,
    }


def close_payload(
    channel_id: str,
    cumulative_amount: str,
    signature: str,
) -> dict[str, Any]:
    """Build a 'close' credential payload."""
    return {
        "action": "close",
        "channelId": channel_id,
        "cumulativeAmount": cumulative_amount,
        "signature": signature,
    }


# ─── Receipt Parsing ────────────────────────────────────────────────────────


def parse_receipt(payment_receipt_header: str) -> dict[str, Any] | None:
    """Parse a Payment-Receipt header (base64url-encoded JSON)."""
    if not payment_receipt_header:
        return None
    try:
        return json.loads(_b64url_decode(payment_receipt_header))
    except Exception:
        return None
