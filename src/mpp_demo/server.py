"""MPP Server — FastAPI + pympp 官方 SDK，支持 charge + session。

启动:
  MPP_RECIPIENT=0x... uv run uvicorn mpp_demo.server:app --port 8000
"""

from __future__ import annotations

import json
import os
import random

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mpp import Challenge
from mpp.server import Mpp
from mpp.methods.tempo import tempo, ChargeIntent, TESTNET_CHAIN_ID, PATH_USD

from mpp.errors import PaymentError, VerificationError

from .config import CHARGE_AMOUNT, SESSION_AMOUNT, RECIPIENT
from .session import SessionVerifier, Voucher

app = FastAPI(title="MPP Demo Server", version="0.1.0")


# ─── Error Handling (RFC 9457 Problem Details) ───────────────────────────────

@app.exception_handler(VerificationError)
async def verification_error_handler(request: Request, exc: VerificationError):
    """Catch pympp VerificationError → structured 402 response."""
    return JSONResponse(
        status_code=402,
        content={
            "type": "https://paymentauth.org/problems/verification-failed",
            "title": "Verification Failed",
            "status": 402,
            "detail": str(exc),
        },
    )


@app.exception_handler(PaymentError)
async def payment_error_handler(request: Request, exc: PaymentError):
    """Catch pympp PaymentError → structured 400 response."""
    return JSONResponse(
        status_code=400,
        content={
            "type": "https://paymentauth.org/problems/payment-error",
            "title": "Payment Error",
            "status": 400,
            "detail": str(exc),
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Catch config errors (missing recipient etc.) → 500 with detail."""
    return JSONResponse(
        status_code=500,
        content={
            "type": "https://paymentauth.org/problems/server-error",
            "title": "Server Configuration Error",
            "status": 500,
            "detail": str(exc),
        },
    )

# ─── MPP Server (charge) ───────────────────────────────────────────────────

_recipient = RECIPIENT or os.getenv("MPP_RECIPIENT", "")
if not _recipient:
    import warnings
    warnings.warn("MPP_RECIPIENT not set — server will fail on payment verification")

mpp = Mpp.create(
    method=tempo(
        currency=PATH_USD,
        recipient=_recipient,
        chain_id=TESTNET_CHAIN_ID,
        intents={"charge": ChargeIntent()},
    ),
    secret_key=os.getenv("MPP_SECRET_KEY", "demo-secret-key-change-in-production"),
)

# ─── Session Verifier (off-chain voucher) ────────────────────────────────────

session_verifier = SessionVerifier()

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

# ─── Pricing (base units, 6 decimals) ───────────────────────────────────────
SESSION_PRICE_PER_IMAGE = 5000  # $0.005
SESSION_DEFAULT_DEPOSIT = 1_000_000  # $1.00


# ─── Charge Endpoints ───────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "MPP Demo Server",
        "chain": "Tempo Moderato Testnet (42431)",
        "endpoints": {
            "/joke": {"intent": "charge", "price": f"${CHARGE_AMOUNT}/request"},
            "/gallery/charge": {"intent": "charge", "price": f"${SESSION_AMOUNT}/image"},
            "/session/open": {"intent": "session", "method": "POST"},
            "/session/gallery": {"intent": "session", "price": "$0.005/image (voucher)"},
            "/session/topup": {"intent": "session", "method": "POST"},
            "/session/close": {"intent": "session", "method": "POST"},
        },
        "protocol": "https://paymentauth.org",
    }


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


# ─── Session Endpoints (off-chain voucher) ───────────────────────────────────

@app.post("/session/open")
async def session_open(request: Request):
    """开通 session — 模拟链上 escrow 存款。

    Body: {"channel_id": "0x...", "payer": "0x...", "deposit": 1000000}
    """
    body = await request.json()
    channel_id = body.get("channel_id")
    payer = body.get("payer")
    deposit = body.get("deposit", SESSION_DEFAULT_DEPOSIT)

    if not channel_id or not payer:
        return JSONResponse(status_code=400, content={"error": "channel_id and payer required"})

    channel = session_verifier.open_channel(channel_id, payer, deposit)
    return {
        "status": "opened",
        "channel_id": channel.channel_id,
        "payer": channel.payer,
        "deposit": channel.deposit,
        "price_per_image": SESSION_PRICE_PER_IMAGE,
    }


@app.post("/session/topup")
async def session_topup(request: Request):
    """追加存款 — 不中断 session。

    Body: {"channel_id": "0x...", "amount": 500000}
    """
    body = await request.json()
    channel_id = body.get("channel_id")
    amount = body.get("amount", 0)
    if not channel_id or amount <= 0:
        return JSONResponse(status_code=400, content={"error": "channel_id and positive amount required"})
    channel = session_verifier.top_up(channel_id, amount)
    if not channel:
        return JSONResponse(status_code=404, content={"error": "channel_not_found"})
    return {
        "status": "topped_up",
        "channel_id": channel.channel_id,
        "new_deposit": channel.deposit,
        "remaining": channel.deposit - channel.cumulative_verified,
    }


@app.post("/session/gallery")
async def session_gallery(request: Request):
    """Session 图库 — 用 EIP-712 voucher 付费，零链上调用。

    Body: {"channel_id": "0x...", "cumulative_amount": 5000,
           "nonce": 1, "signature": "0x...", "signer": "0x..."}
    """
    body = await request.json()

    voucher = Voucher(
        channel_id=body["channel_id"],
        cumulative_amount=body["cumulative_amount"],
        nonce=body["nonce"],
        signature=body["signature"],
        signer=body["signer"],
    )

    ok, delta, err = session_verifier.verify_voucher(voucher)
    if not ok:
        return JSONResponse(status_code=402, content={"error": err, "detail": "Voucher verification failed"})

    image = random.choice(GALLERY)
    channel = session_verifier.get_channel(voucher.channel_id)
    return {
        "image": image,
        "payer": voucher.signer,
        "session": {
            "channel_id": voucher.channel_id,
            "delta": delta,
            "cumulative_spent": channel.cumulative_verified if channel else 0,
            "remaining": (channel.deposit - channel.cumulative_verified) if channel else 0,
        },
    }


@app.post("/session/close")
async def session_close(request: Request):
    """关闭 session — 结算退款。"""
    body = await request.json()
    channel_id = body.get("channel_id")
    if not channel_id:
        return JSONResponse(status_code=400, content={"error": "channel_id required"})
    result = session_verifier.close_channel(channel_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": "channel_not_found"})
    return {"status": "closed", **result}
