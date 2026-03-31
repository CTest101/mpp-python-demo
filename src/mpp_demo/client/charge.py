"""MPP Client — charge (链上) + session (HTTP 402 protocol)。"""

from __future__ import annotations

from mpp.client import Client
from mpp.methods.tempo import ChargeIntent, TESTNET_CHAIN_ID

from ..signer import Signer, SignerTempoMethod


def _make_method(signer: Signer) -> SignerTempoMethod:
    """用 Signer 创建 SignerTempoMethod。"""
    method = SignerTempoMethod(
        signer=signer,
        chain_id=TESTNET_CHAIN_ID,
        intents={"charge": ChargeIntent()},
    )
    for intent in method._intents.values():
        if hasattr(intent, "rpc_url") and intent.rpc_url is None:
            intent.rpc_url = method.rpc_url
        if hasattr(intent, "_method"):
            intent._method = method
    return method


# ─── Charge Mode ─────────────────────────────────────────────────────────────

async def charge_joke(signer: Signer, server: str) -> dict:
    """Charge — 买一个笑话（链上结算）。"""
    method = _make_method(signer)
    async with Client(methods=[method]) as client:
        response = await client.get(f"{server}/joke")
        print(f"  HTTP {response.status_code}")
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "body": response.text[:200]}
        return response.json()


async def charge_gallery(signer: Signer, server: str, count: int = 3) -> list[dict]:
    """Charge — 买图（每次链上结算）。"""
    method = _make_method(signer)
    results = []
    async with Client(methods=[method]) as client:
        for i in range(count):
            response = await client.get(f"{server}/gallery/charge")
            if response.status_code != 200:
                print(f"  [{i+1}] ❌ HTTP {response.status_code}")
                break
            data = response.json()
            results.append(data)
            img = data.get("image", {})
            print(f"  [{i+1}] {img.get('title', '?')} — ${0.005}")
    return results


# ─── Session Mode (HTTP 402 protocol) ────────────────────────────────────────

async def session_gallery(signer: Signer, server: str, count: int = 5, deposit: int = 1_000_000) -> list[dict]:
    """Session — 买图（HTTP 402 protocol，off-chain voucher）。"""
    from .session import SessionHttpClient

    results = []
    async with SessionHttpClient(signer=signer, max_deposit=deposit) as client:
        for i in range(count):
            response = await client.fetch(f"{server}/gallery")

            if response.status_code != 200:
                print(f"  [{i+1}] ❌ HTTP {response.status_code}: {response.text[:200]}")
                break

            data = response.json()
            results.append(data)
            img = data.get("image", {})
            print(f"  [{i+1}] {img.get('title', '?')} | cumulative: ${client.cumulative_amount / 1e6:.4f}")

        # Close channel
        print(f"\n  ⛓️  Closing channel (cumulative: ${client.cumulative_amount / 1e6:.4f})...")
        receipt = await client.close(f"{server}/gallery")
        if receipt:
            print(f"  📊 Receipts collected: {len(client.receipts)}")

    return results
