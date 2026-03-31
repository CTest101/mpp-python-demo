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


# ─── Server-side: Challenge Building ────────────────────────────────────────


def _canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace (matches ox Json.canonicalize)."""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _compute_challenge_id(
    realm: str,
    method: str,
    intent: str,
    request_b64: str,
    expires: str,
    secret_key: str,
    digest: str = "",
    opaque: str = "",
) -> str:
    """Compute HMAC-SHA256 challenge ID (matches mppx Challenge.computeId).

    input = realm|method|intent|request_b64|expires|digest|opaque
    id = base64url(HMAC-SHA256(secretKey, input))
    """
    import hmac
    import hashlib

    input_str = "|".join([realm, method, intent, request_b64, expires, digest, opaque])
    mac = hmac.new(
        secret_key.encode("utf-8"),
        input_str.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(mac)


def build_session_challenge(
    secret_key: str,
    realm: str,
    amount: str,
    currency: str,
    recipient: str,
    escrow_contract: str,
    chain_id: int,
    expires_minutes: int = 5,
    unit_type: str = "image",
) -> str:
    """Build a WWW-Authenticate: Payment header for session intent.

    Returns the full header value.
    """
    from datetime import datetime, timezone, timedelta

    expires = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat()

    request_obj = {
        "amount": amount,
        "currency": currency,
        "methodDetails": {
            "chainId": chain_id,
            "escrowContract": escrow_contract,
        },
        "recipient": recipient,
        "unitType": unit_type,
    }
    request_b64 = _b64url_encode(_canonical_json(request_obj).encode("utf-8"))

    challenge_id = _compute_challenge_id(
        realm=realm,
        method="tempo",
        intent="session",
        request_b64=request_b64,
        expires=expires,
        secret_key=secret_key,
    )

    return (
        f'Payment id="{challenge_id}", '
        f'realm="{realm}", '
        f'method="tempo", '
        f'intent="session", '
        f'request="{request_b64}", '
        f'expires="{expires}"'
    )


def verify_challenge_hmac(challenge_echo: dict, secret_key: str) -> bool:
    """Verify that a challenge echo's ID matches the HMAC.

    The challenge echo from the credential must have been issued by this server.
    """
    # Use preserved original b64 if available, otherwise re-serialize
    request_b64 = challenge_echo.get("_request_b64", "")
    if not request_b64:
        request_obj = challenge_echo.get("request")
        if isinstance(request_obj, str):
            request_b64 = request_obj
        elif isinstance(request_obj, dict):
            request_b64 = _b64url_encode(_canonical_json(request_obj).encode("utf-8"))
        else:
            return False

    expected_id = _compute_challenge_id(
        realm=challenge_echo.get("realm", ""),
        method=challenge_echo.get("method", ""),
        intent=challenge_echo.get("intent", ""),
        request_b64=request_b64,
        expires=challenge_echo.get("expires", ""),
        secret_key=secret_key,
    )
    return _constant_time_compare(challenge_echo.get("id", ""), expected_id)


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    import hmac as _hmac
    return _hmac.compare_digest(a.encode(), b.encode())


def parse_credential_from_request(auth_header: str) -> dict[str, Any]:
    """Parse Authorization: Payment <base64url> header into credential dict."""
    if not auth_header.lower().startswith("payment "):
        raise ValueError("Missing Payment scheme")
    encoded = auth_header[8:].strip()
    try:
        decoded = json.loads(_b64url_decode(encoded))
    except Exception:
        raise ValueError("Invalid base64url or JSON in credential")

    # Deserialize challenge.request from base64url to dict
    challenge = decoded.get("challenge", {})
    request_str = challenge.get("request", "")
    if isinstance(request_str, str) and request_str:
        try:
            challenge["request"] = json.loads(_b64url_decode(request_str))
            challenge["_request_b64"] = request_str  # preserve original for HMAC
        except Exception:
            pass

    return decoded


def build_session_receipt(
    channel_id: str,
    challenge_id: str,
    accepted_cumulative: str,
    tx_hash: str | None = None,
) -> str:
    """Build a Payment-Receipt header value (base64url-encoded JSON)."""
    from datetime import datetime, timezone

    receipt = {
        "method": "tempo",
        "intent": "session",
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reference": channel_id,
        "challengeId": challenge_id,
        "channelId": channel_id,
        "acceptedCumulative": accepted_cumulative,
    }
    if tx_hash:
        receipt["txHash"] = tx_hash

    return _b64url_encode(json.dumps(receipt, separators=(",", ":")).encode("utf-8"))
