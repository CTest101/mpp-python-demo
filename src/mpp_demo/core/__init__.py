"""Core MPP primitives — config, protocol, voucher signing, escrow client."""

from .config import (
    TEMPO_CHAIN_ID,
    TEMPO_RPC,
    PATH_USD_ADDRESS,
    SERVER_HOST,
    SERVER_PORT,
    RECIPIENT,
    CHARGE_AMOUNT,
    SESSION_AMOUNT,
)
from .voucher import (
    ESCROW_CONTRACT,
    VOUCHER_TYPEHASH,
    DOMAIN_SEPARATOR,
    SESSION_DOMAIN,
    Voucher,
    SessionClient,
    compute_voucher_digest,
)
from .protocol import (
    PaymentChallenge,
    parse_challenge,
    parse_challenge_from_response,
    build_authorization_header,
    open_payload,
    voucher_payload,
    close_payload,
    parse_receipt,
    build_session_challenge,
    verify_challenge_hmac,
    parse_credential_from_request,
    build_session_receipt,
)

__all__ = [
    "TEMPO_CHAIN_ID", "TEMPO_RPC", "PATH_USD_ADDRESS",
    "SERVER_HOST", "SERVER_PORT", "RECIPIENT",
    "CHARGE_AMOUNT", "SESSION_AMOUNT",
    "ESCROW_CONTRACT", "VOUCHER_TYPEHASH", "DOMAIN_SEPARATOR", "SESSION_DOMAIN",
    "Voucher", "SessionClient", "compute_voucher_digest",
    "PaymentChallenge", "parse_challenge", "parse_challenge_from_response",
    "build_authorization_header", "open_payload", "voucher_payload",
    "close_payload", "parse_receipt",
    "build_session_challenge", "verify_challenge_hmac",
    "parse_credential_from_request", "build_session_receipt",
]
