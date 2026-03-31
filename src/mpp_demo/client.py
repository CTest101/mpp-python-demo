"""MPP Client — charge (链上) + session (HTTP 402 protocol)。

用法:
  python -m mpp_demo.client charge                           # 买一个笑话
  python -m mpp_demo.client gallery --count 3                # charge 买 3 张图
  python -m mpp_demo.client session --count 5                # session 买 5 张图 (402 protocol)
"""

from __future__ import annotations

import asyncio
import random

import httpx
from mpp.client import Client
from mpp.methods.tempo import ChargeIntent, TESTNET_CHAIN_ID

from .config import SERVER_HOST
from .signer import Signer, signer_from_env, SignerTempoMethod


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
    from .session_http import SessionHttpClient

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


# ─── CLI ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MPP Client CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("charge", help="Buy a joke (charge, on-chain)").add_argument("--server", default=SERVER_HOST)
    gp = sub.add_parser("gallery", help="Buy images (charge, on-chain)")
    gp.add_argument("--count", type=int, default=3)
    gp.add_argument("--server", default=SERVER_HOST)
    sp = sub.add_parser("session", help="Buy images (session, 402 protocol)")
    sp.add_argument("--count", type=int, default=5)
    sp.add_argument("--deposit", type=int, default=1_000_000, help="Deposit in base units (default $1.00)")
    sp.add_argument("--server", default="http://localhost:5555")

    args = parser.parse_args()
    signer = signer_from_env()
    print(f"🔑 Signer: {signer}")
    print(f"📍 Address: {signer.address}")
    print(f"🔐 Signing via: {signer.__class__.__name__}")

    try:
        if args.command == "charge":
            print("\n💰 Charge mode — buying a joke (on-chain)...")
            result = await charge_joke(signer, args.server)
            if "joke" in result:
                print(f"🎭 {result['joke']}")
                print(f"💳 Payer: {result.get('payer', '?')}")
            else:
                print(f"❌ {result}")

        elif args.command == "gallery":
            print(f"\n🖼️  Gallery (charge) — buying {args.count} images on-chain...")
            results = await charge_gallery(signer, args.server, args.count)
            print(f"\n📊 Got {len(results)} images")

        elif args.command == "session":
            print(f"\n⚡ Session (402 protocol) — buying {args.count} images...")
            results = await session_gallery(signer, args.server, args.count, args.deposit)
            print(f"📊 Got {len(results)} images (402 session protocol!)")

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
