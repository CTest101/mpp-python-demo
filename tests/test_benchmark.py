"""Benchmark: session voucher sign + verify latency."""

import time
import pytest
from mpp_demo.signer import LocalSigner
from mpp_demo.session import SessionClient, SessionVerifier

TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

ITERATIONS = 100


@pytest.mark.anyio
async def test_voucher_sign_verify_latency():
    """Benchmark: sign + verify 100 vouchers, report avg latency."""
    signer = LocalSigner(TEST_KEY)
    channel_id = "0x" + "bb" * 32
    session = SessionClient(signer=signer, channel_id=channel_id)
    verifier = SessionVerifier()
    verifier.open_channel(channel_id, TEST_ADDRESS, deposit=ITERATIONS * 5000 + 100_000)

    # Warmup
    v = await session.sign_voucher(5000)
    verifier.verify_voucher(v)

    # Benchmark sign
    t0 = time.perf_counter()
    vouchers = []
    for _ in range(ITERATIONS):
        vouchers.append(await session.sign_voucher(5000))
    sign_elapsed = time.perf_counter() - t0

    # Benchmark verify
    t1 = time.perf_counter()
    for v in vouchers:
        ok, _, err = verifier.verify_voucher(v)
        assert ok, f"verify failed: {err}"
    verify_elapsed = time.perf_counter() - t1

    sign_avg_ms = (sign_elapsed / ITERATIONS) * 1000
    verify_avg_ms = (verify_elapsed / ITERATIONS) * 1000

    print(f"\n📊 Benchmark ({ITERATIONS} vouchers):")
    print(f"  Sign:   {sign_avg_ms:.2f} ms/voucher ({sign_elapsed:.3f}s total)")
    print(f"  Verify: {verify_avg_ms:.2f} ms/voucher ({verify_elapsed:.3f}s total)")
    print(f"  Total:  {sign_avg_ms + verify_avg_ms:.2f} ms/round-trip")

    # Sanity: verify should be under 5ms per voucher on most hardware
    assert verify_avg_ms < 50, f"Verify too slow: {verify_avg_ms:.2f}ms"
