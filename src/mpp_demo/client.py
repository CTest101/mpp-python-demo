"""MPP Client — charge (链上) + session (off-chain voucher) + session-onchain (真实链上 escrow)。

用法:
  python -m mpp_demo.client charge                           # 买一个笑话
  python -m mpp_demo.client gallery --count 3                # charge 买 3 张图
  python -m mpp_demo.client session --count 5                # session 买 5 张图 (内存模拟)
  python -m mpp_demo.client session-onchain --count 5        # session 买 5 张图 (链上 escrow)
"""

from __future__ import annotations

import asyncio

import httpx
from mpp.client import Client
from mpp.methods.tempo import ChargeIntent, TESTNET_CHAIN_ID

from .config import SERVER_HOST
from .session import SessionClient
from .session_onchain import OnchainSessionClient
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


# ─── Session Mode ────────────────────────────────────────────────────────────

async def session_gallery(signer: Signer, server: str, count: int = 5) -> list[dict]:
    """Session — 买图（off-chain voucher，零链上调用）。"""
    session = SessionClient(signer=signer)
    results = []

    async with httpx.AsyncClient(timeout=30.0) as http:
        # 1. Open session
        print(f"  📂 Opening session channel: {session.channel_id[:18]}...")
        open_resp = await http.post(f"{server}/session/open", json={
            "channel_id": session.channel_id,
            "payer": signer.address,
            "deposit": 1_000_000,  # $1.00
        })
        open_data = open_resp.json()
        print(f"  ✅ Channel opened: deposit ${open_data['deposit'] / 1_000_000:.2f}")

        # 2. Buy images with vouchers
        price = open_data.get("price_per_image", 5000)
        for i in range(count):
            voucher = await session.sign_voucher(amount_delta=price)
            resp = await http.post(f"{server}/session/gallery", json={
                "channel_id": voucher.channel_id,
                "cumulative_amount": voucher.cumulative_amount,
                "nonce": voucher.nonce,
                "signature": voucher.signature,
                "signer": voucher.signer,
            })
            if resp.status_code != 200:
                print(f"  [{i+1}] ❌ {resp.json().get('error', resp.status_code)}")
                break
            data = resp.json()
            results.append(data)
            s = data["session"]
            img = data.get("image", {})
            print(f"  [{i+1}] {img.get('title', '?')} | delta: ${s['delta']/1e6:.4f} | spent: ${s['cumulative_spent']/1e6:.4f} | remaining: ${s['remaining']/1e6:.4f}")

        # 3. Close session
        close_resp = await http.post(f"{server}/session/close", json={
            "channel_id": session.channel_id,
        })
        close_data = close_resp.json()
        print(f"\n  ✅ Session closed: spent ${close_data['total_spent']/1e6:.4f}, refund ${close_data['refund']/1e6:.4f}")

    return results


# ─── Session On-chain Mode ───────────────────────────────────────────────────

async def session_onchain_gallery(signer: Signer, server: str, count: int = 5, deposit: int = 1_000_000) -> list[dict]:
    """Session On-chain — 链上 escrow open → off-chain vouchers → 链上 close。"""
    results = []

    async with httpx.AsyncClient(timeout=60.0) as http:
        # 0. Get server's payee address
        info_resp = await http.get(f"{server}/session-onchain/info")
        server_info = info_resp.json()
        payee = server_info["payee"]
        price = server_info.get("price_per_image", 5000)
        print(f"  📡 Server payee: {payee}")

        # 1. Open channel on-chain
        client = OnchainSessionClient(signer=signer, payee=payee)
        print(f"  ⛓️  Opening channel on-chain (approve + open, deposit ${deposit/1e6:.2f})...")
        channel_id, tx_hash = await client.open_channel(deposit=deposit)
        print(f"  ✅ Channel opened: {channel_id[:18]}...")
        print(f"  📝 TX: {tx_hash}")

        # 2. Register channel with server
        open_resp = await http.post(f"{server}/session-onchain/open", json={
            "channel_id": channel_id,
            "payer": signer.address,
            "deposit": deposit,
        })
        open_data = open_resp.json()
        print(f"  🤝 Server registered channel: deposit ${open_data['deposit'] / 1e6:.2f}")

        # 3. Buy images with off-chain vouchers
        for i in range(count):
            voucher = await client.sign_voucher(amount_delta=price)
            resp = await http.post(f"{server}/session-onchain/gallery", json={
                "channel_id": voucher.channel_id,
                "cumulative_amount": voucher.cumulative_amount,
                "nonce": voucher.nonce,
                "signature": voucher.signature,
                "signer": voucher.signer,
            })
            if resp.status_code != 200:
                print(f"  [{i+1}] ❌ {resp.json().get('error', resp.status_code)}")
                break
            data = resp.json()
            results.append(data)
            s = data["session"]
            img = data.get("image", {})
            print(f"  [{i+1}] {img.get('title', '?')} | delta: ${s['delta']/1e6:.4f} | spent: ${s['cumulative_spent']/1e6:.4f} | remaining: ${s['remaining']/1e6:.4f}")

        # 4. Request server to close channel on-chain
        print(f"\n  ⛓️  Requesting on-chain close...")
        close_resp = await http.post(f"{server}/session-onchain/close", json={
            "channel_id": channel_id,
        })
        close_data = close_resp.json()
        print(f"  ✅ Channel closed on-chain!")
        print(f"     Spent: ${close_data.get('total_spent', 0)/1e6:.4f}")
        print(f"     Refund: ${close_data.get('refund', 0)/1e6:.4f}")
        if close_data.get("tx_hash"):
            print(f"     TX: {close_data['tx_hash']}")

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
    sp = sub.add_parser("session", help="Buy images (session, off-chain voucher)")
    sp.add_argument("--count", type=int, default=5)
    sp.add_argument("--server", default=SERVER_HOST)
    sop = sub.add_parser("session-onchain", help="Buy images (on-chain escrow session)")
    sop.add_argument("--count", type=int, default=5)
    sop.add_argument("--deposit", type=int, default=1_000_000, help="Deposit in base units (default $1.00)")
    sop.add_argument("--server", default=SERVER_HOST)

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
            print(f"\n⚡ Session mode — buying {args.count} images (off-chain voucher)...")
            results = await session_gallery(signer, args.server, args.count)
            print(f"📊 Got {len(results)} images (zero on-chain tx!)")

        elif args.command == "session-onchain":
            print(f"\n⛓️  Session On-chain — buying {args.count} images (real escrow)...")
            results = await session_onchain_gallery(signer, args.server, args.count, args.deposit)
            print(f"📊 Got {len(results)} images (on-chain escrow!)")

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
