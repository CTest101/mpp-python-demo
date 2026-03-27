"""Tests for on-chain session server endpoints.

Tests the HTTP API layer without actual RPC calls.
"""

import os
import pytest
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing server module
os.environ.setdefault("MPP_RECIPIENT", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
os.environ.setdefault(
    "MPP_SERVER_PRIVATE_KEY",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_session_onchain_info():
    """GET /session-onchain/info returns server payee info."""
    from mpp_demo.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/session-onchain/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "payee" in data
    assert "escrow" in data
    assert "price_per_image" in data


@pytest.mark.anyio
async def test_session_onchain_open():
    """POST /session-onchain/open registers a channel."""
    from mpp_demo.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/session-onchain/open", json={
            "channel_id": "0x" + "aa" * 32,
            "payer": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
            "deposit": 1_000_000,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "opened"
    assert data["deposit"] == 1_000_000


@pytest.mark.anyio
async def test_session_onchain_gallery_without_open():
    """POST /session-onchain/gallery without open returns 402."""
    from mpp_demo.server import app
    from mpp_demo.signer import LocalSigner
    from mpp_demo.session import SessionClient

    signer = LocalSigner("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
    session = SessionClient(signer=signer, channel_id="0x" + "bb" * 32)
    voucher = await session.sign_voucher(5000)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/session-onchain/gallery", json={
            "channel_id": voucher.channel_id,
            "cumulative_amount": voucher.cumulative_amount,
            "nonce": voucher.nonce,
            "signature": voucher.signature,
            "signer": voucher.signer,
        })
    assert resp.status_code == 402


@pytest.mark.anyio
async def test_session_onchain_open_missing_fields():
    """POST /session-onchain/open without required fields returns 400."""
    from mpp_demo.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/session-onchain/open", json={"channel_id": "0x" + "cc" * 32})
    assert resp.status_code == 400
