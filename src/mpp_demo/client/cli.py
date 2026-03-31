"""MPP Client CLI entry point.

用法:
  python -m mpp_demo charge                           # 买一个笑话
  python -m mpp_demo gallery --count 3                # charge 买 3 张图
  python -m mpp_demo session --count 5                # session 买 5 张图 (402 protocol)
"""

from __future__ import annotations

import asyncio

from ..core.config import SERVER_HOST
from ..signer import signer_from_env
from .charge import charge_joke, charge_gallery, session_gallery


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
