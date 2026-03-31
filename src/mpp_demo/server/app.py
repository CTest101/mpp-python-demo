"""MPP Server — FastAPI + pympp SDK, 支持 charge (pympp) + session (402 protocol).

Session 端点使用标准 HTTP 402 Payment Authentication Scheme:
  GET /gallery → 402 + WWW-Authenticate: Payment intent="session"
  GET /gallery + Authorization: Payment {action: "open/voucher/close"} → 200

启动:
  MPP_RECIPIENT=0x... MPP_SERVER_PRIVATE_KEY=0x... uv run uvicorn mpp_demo.server.app:app --port 8000
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mpp import Challenge
from mpp.server import Mpp
from mpp.methods.tempo import tempo, ChargeIntent, TESTNET_CHAIN_ID, PATH_USD

from mpp.errors import PaymentError, VerificationError

from ..core.config import CHARGE_AMOUNT, SESSION_AMOUNT, RECIPIENT
from ..core.voucher import Voucher, ESCROW_CONTRACT
from ..core.escrow import EscrowClient, ESCROW_ADDRESS
from ..core.protocol import (
    PaymentChallenge,
    build_session_challenge,
    parse_credential_from_request,
    build_session_receipt,
    _b64url_encode,
)
from .verifier import SessionVerifier

app = FastAPI(title="MPP Demo Server", version="0.2.0")


# ─── Error Handling (RFC 9457 Problem Details) ───────────────────────────────

@app.exception_handler(VerificationError)
async def verification_error_handler(request: Request, exc: VerificationError):
    return JSONResponse(status_code=402, content={
        "type": "https://paymentauth.org/problems/verification-failed",
        "title": "Verification Failed", "status": 402, "detail": str(exc),
    })

@app.exception_handler(PaymentError)
async def payment_error_handler(request: Request, exc: PaymentError):
    return JSONResponse(status_code=400, content={
        "type": "https://paymentauth.org/problems/payment-error",
        "title": "Payment Error", "status": 400, "detail": str(exc),
    })

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=500, content={
        "type": "https://paymentauth.org/problems/server-error",
        "title": "Server Configuration Error", "status": 500, "detail": str(exc),
    })


# ─── Config ─────────────────────────────────────────────────────────────────

_recipient = RECIPIENT or os.getenv("MPP_RECIPIENT", "")
_secret_key = os.getenv("MPP_SECRET_KEY", "demo-secret-key-change-in-production")
_server_key = os.getenv("MPP_SERVER_PRIVATE_KEY", "")

if not _recipient:
    import warnings
    warnings.warn("MPP_RECIPIENT not set — server will fail on payment verification")


# ─── MPP Charge (pympp SDK) ─────────────────────────────────────────────────

mpp = Mpp.create(
    method=tempo(
        currency=PATH_USD,
        recipient=_recipient,
        chain_id=TESTNET_CHAIN_ID,
        intents={"charge": ChargeIntent()},
    ),
    secret_key=_secret_key,
)


# ─── Session Verifier (off-chain voucher) ────────────────────────────────────

session_verifier = SessionVerifier()

# ─── On-chain Session Server (for close/settle) ─────────────────────────────

_escrow_client: EscrowClient | None = None


def _get_escrow_client() -> EscrowClient:
    """Lazily initialize escrow client for on-chain close."""
    global _escrow_client
    if _escrow_client is None:
        if not _server_key:
            raise ValueError("MPP_SERVER_PRIVATE_KEY required for session close")
        from ..signer import LocalSigner
        signer = LocalSigner(_server_key)
        _escrow_client = EscrowClient(signer=signer)
    return _escrow_client


# ─── Data ────────────────────────────────────────────────────────────────────

JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs. 🪲",
    "There are 10 types of people: those who understand binary, and those who don't.",
    "A SQL query walks into a bar, sees two tables, and asks: 'Can I JOIN you?'",
    "!false — it's funny because it's true.",
    "A programmer's wife tells him: 'Go buy a loaf of bread. If they have eggs, get a dozen.' He comes home with 12 loaves. 🍞",
    "Why do Java developers wear glasses? Because they don't C#.",
    "Debugging: removing bugs. Programming: adding them.",
]

GALLERY = [
    {"id": 1, "url": "https://picsum.photos/400/300?random=1", "title": "Mountain Dawn"},
    {"id": 2, "url": "https://picsum.photos/400/300?random=2", "title": "Ocean Breeze"},
    {"id": 3, "url": "https://picsum.photos/400/300?random=3", "title": "City Lights"},
    {"id": 4, "url": "https://picsum.photos/400/300?random=4", "title": "Forest Path"},
    {"id": 5, "url": "https://picsum.photos/400/300?random=5", "title": "Desert Sun"},
]

SESSION_PRICE_PER_IMAGE = 5000  # $0.005
SESSION_DEFAULT_DEPOSIT = 1_000_000  # $1.00


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "MPP Demo Server (Python)",
        "version": "0.2.0",
        "chain": "Tempo Moderato Testnet (42431)",
        "recipient": _recipient,
        "endpoints": {
            "/health": {"mode": "free"},
            "/joke": {"mode": "charge", "price": f"${CHARGE_AMOUNT}/request"},
            "/gallery/charge": {"mode": "charge", "price": f"${SESSION_AMOUNT}/image"},
            "/gallery": {"mode": "session", "price": "$0.005/image (402 protocol)"},
        },
        "protocol": "https://paymentauth.org",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "recipient": _recipient}


# ─── Charge Endpoints (pympp SDK) ───────────────────────────────────────────

@app.get("/joke")
async def get_joke(request: Request):
    """付费笑话 — charge 模式，$0.01/次，链上结算。"""
    auth = request.headers.get("Authorization")
    result = await mpp.charge(authorization=auth, amount=CHARGE_AMOUNT,
                               description=f"One programmer joke (${CHARGE_AMOUNT})")
    if isinstance(result, Challenge):
        return JSONResponse(status_code=402,
            content={"error": "payment_required", "detail": f"This joke costs ${CHARGE_AMOUNT}"},
            headers={"WWW-Authenticate": result.to_www_authenticate(mpp.realm), "Cache-Control": "no-store"})
    credential, receipt = result
    return JSONResponse(
        content={"joke": random.choice(JOKES), "payer": credential.source},
        headers={"Payment-Receipt": receipt.to_payment_receipt(), "Cache-Control": "private"})


@app.get("/gallery/charge")
async def gallery_charge(request: Request):
    """付费图库 — charge 模式，$0.005/次，链上结算。"""
    auth = request.headers.get("Authorization")
    result = await mpp.charge(authorization=auth, amount=SESSION_AMOUNT,
                               description=f"One gallery image (${SESSION_AMOUNT})")
    if isinstance(result, Challenge):
        return JSONResponse(status_code=402,
            content={"error": "payment_required", "detail": f"Each image costs ${SESSION_AMOUNT}"},
            headers={"WWW-Authenticate": result.to_www_authenticate(mpp.realm), "Cache-Control": "no-store"})
    credential, receipt = result
    return JSONResponse(
        content={"image": random.choice(GALLERY), "payer": credential.source},
        headers={"Payment-Receipt": receipt.to_payment_receipt(), "Cache-Control": "private"})


# ─── Session Endpoint (402 protocol) ────────────────────────────────────────

@app.get("/gallery")
async def gallery_session(request: Request):
    """付费图库 — session 模式，HTTP 402 协议。

    无 Authorization → 402 + WWW-Authenticate (session challenge)
    有 Authorization → 解析 credential → 处理 open/voucher/close
    """
    auth = request.headers.get("Authorization")

    if not auth or not auth.lower().startswith("payment "):
        # No credential → issue session challenge
        challenge_header = build_session_challenge(
            secret_key=_secret_key,
            realm=request.url.hostname or "localhost",
            amount=str(SESSION_PRICE_PER_IMAGE),
            currency=str(PATH_USD),
            recipient=_recipient,
            escrow_contract=ESCROW_ADDRESS,
            chain_id=TESTNET_CHAIN_ID,
        )
        return JSONResponse(
            status_code=402,
            content={
                "type": "https://paymentauth.org/problems/payment-required",
                "title": "Payment Required",
                "status": 402,
                "detail": "Payment is required.",
            },
            headers={
                "WWW-Authenticate": challenge_header,
                "Cache-Control": "no-store",
            },
        )

    # Parse credential
    try:
        credential = parse_credential_from_request(auth)
    except Exception as e:
        return JSONResponse(status_code=400, content={
            "type": "https://paymentauth.org/problems/bad-request",
            "title": "Bad Request", "status": 400, "detail": str(e),
        })

    # Verify challenge HMAC
    from ..core.protocol import verify_challenge_hmac
    if not verify_challenge_hmac(credential["challenge"], _secret_key):
        return JSONResponse(status_code=402, content={
            "type": "https://paymentauth.org/problems/invalid-challenge",
            "title": "Invalid Challenge", "status": 402,
            "detail": f'Challenge "{credential["challenge"]["id"]}" was not issued by this server.',
        }, headers={"Cache-Control": "no-store"})

    payload = credential["payload"]
    action = payload.get("action", "")

    if action == "open":
        return await _handle_session_open(credential, payload)
    elif action == "voucher":
        return await _handle_session_voucher(credential, payload)
    elif action == "close":
        return await _handle_session_close(credential, payload)
    else:
        return JSONResponse(status_code=400, content={
            "error": "unknown_action", "detail": f"Unknown action: {action}",
        })


async def _handle_session_open(credential: dict, payload: dict) -> JSONResponse:
    """Handle open credential — broadcast tx + register channel."""
    channel_id = payload.get("channelId", "")
    transaction = payload.get("transaction", "")
    signature = payload.get("signature", "")
    cumulative_amount = int(payload.get("cumulativeAmount", "0"))

    if not channel_id or not transaction:
        return JSONResponse(status_code=400, content={"error": "channelId and transaction required"})

    # Broadcast the signed transaction
    from ..core.escrow import _send_tx, _wait_for_receipt
    from ..core.config import TEMPO_RPC
    try:
        tx_hash = await _send_tx(TEMPO_RPC, transaction)
        await _wait_for_receipt(TEMPO_RPC, tx_hash)
    except Exception as e:
        return JSONResponse(status_code=402, content={
            "type": "https://paymentauth.org/problems/verification-failed",
            "title": "Verification Failed", "status": 402,
            "detail": f"Transaction broadcast failed: {e}",
        })

    # Read deposit from on-chain (simplified: trust the credential)
    # In production, read escrow.getChannel(channelId) to verify deposit
    source = credential.get("source", "")
    payer = source.split(":")[-1] if source else ""

    # Register channel for voucher verification
    session_verifier.open_channel(channel_id, payer, SESSION_DEFAULT_DEPOSIT)

    # Verify the initial voucher
    voucher = Voucher(
        channel_id=channel_id,
        cumulative_amount=cumulative_amount,
        nonce=1,
        signature=signature,
        signer=payer,
    )
    ok, delta, err = session_verifier.verify_voucher(voucher)
    if not ok:
        return JSONResponse(status_code=402, content={"error": err})

    # Serve content
    image = random.choice(GALLERY)
    receipt = build_session_receipt(
        channel_id=channel_id,
        challenge_id=credential["challenge"]["id"],
        accepted_cumulative=str(cumulative_amount),
        tx_hash=tx_hash,
    )
    return JSONResponse(
        content={"image": image},
        headers={"Payment-Receipt": receipt, "Cache-Control": "private"},
    )


async def _handle_session_voucher(credential: dict, payload: dict) -> JSONResponse:
    """Handle voucher credential — verify signature, serve content."""
    channel_id = payload.get("channelId", "")
    cumulative_amount = int(payload.get("cumulativeAmount", "0"))
    signature = payload.get("signature", "")

    source = credential.get("source", "")
    payer = source.split(":")[-1] if source else ""

    channel = session_verifier.get_channel(channel_id)
    if not channel:
        return JSONResponse(status_code=402, content={"error": "channel_not_found"})

    voucher = Voucher(
        channel_id=channel_id,
        cumulative_amount=cumulative_amount,
        nonce=channel.last_nonce + 1,  # auto-increment
        signature=signature,
        signer=payer,
    )
    ok, delta, err = session_verifier.verify_voucher(voucher)
    if not ok:
        return JSONResponse(status_code=402, content={"error": err})

    image = random.choice(GALLERY)
    receipt = build_session_receipt(
        channel_id=channel_id,
        challenge_id=credential["challenge"]["id"],
        accepted_cumulative=str(cumulative_amount),
    )
    return JSONResponse(
        content={"image": image},
        headers={"Payment-Receipt": receipt, "Cache-Control": "private"},
    )


async def _handle_session_close(credential: dict, payload: dict) -> JSONResponse:
    """Handle close credential — settle on-chain."""
    channel_id = payload.get("channelId", "")
    cumulative_amount = int(payload.get("cumulativeAmount", "0"))
    signature = payload.get("signature", "")

    channel = session_verifier.get_channel(channel_id)
    if not channel:
        return JSONResponse(status_code=404, content={"error": "channel_not_found"})

    # On-chain settle
    tx_hash = None
    if _server_key:
        try:
            escrow = _get_escrow_client()
            sig_bytes = bytes.fromhex(
                signature[2:] if signature.startswith("0x") else signature
            )
            tx_hash = await escrow.close(channel_id, cumulative_amount, sig_bytes)
        except Exception as e:
            return JSONResponse(status_code=500, content={
                "error": f"On-chain close failed: {e}",
            })

    # Clean up
    session_verifier.close_channel(channel_id)

    receipt = build_session_receipt(
        channel_id=channel_id,
        challenge_id=credential["challenge"]["id"],
        accepted_cumulative=str(cumulative_amount),
        tx_hash=tx_hash,
    )
    return JSONResponse(
        status_code=204 if tx_hash else 200,
        content=None,
        headers={"Payment-Receipt": receipt},
    )
