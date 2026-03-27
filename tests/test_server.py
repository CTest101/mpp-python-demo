"""Tests for the MPP server endpoints."""

import os
import pytest
from httpx import ASGITransport, AsyncClient

# Set recipient before importing server module
os.environ.setdefault("MPP_RECIPIENT", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_root():
    from mpp_demo.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "MPP Demo Server"
    assert "/joke" in data["endpoints"]


@pytest.mark.anyio
async def test_joke_returns_402():
    """GET /joke without auth should return 402."""
    from mpp_demo.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/joke")
    assert resp.status_code == 402
    assert "WWW-Authenticate" in resp.headers
    assert resp.headers["WWW-Authenticate"].startswith("Payment ")


@pytest.mark.anyio
async def test_gallery_returns_402():
    """GET /gallery without auth should return 402."""
    from mpp_demo.server import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/gallery/charge")
    assert resp.status_code == 402
    assert "WWW-Authenticate" in resp.headers
