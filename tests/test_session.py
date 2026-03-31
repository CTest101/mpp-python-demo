"""Tests for the Session (off-chain voucher) system."""

import pytest
from mpp_demo.signer import LocalSigner
from mpp_demo.core.voucher import SessionClient, Voucher
from mpp_demo.server.verifier import SessionVerifier

TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class TestSessionClient:
    @pytest.mark.anyio
    async def test_sign_voucher(self):
        signer = LocalSigner(TEST_KEY)
        session = SessionClient(signer=signer, channel_id="0x" + "ab" * 32)
        voucher = await session.sign_voucher(amount_delta=5000)
        assert voucher.cumulative_amount == 5000
        assert voucher.nonce == 1
        assert voucher.signer == TEST_ADDRESS
        assert voucher.signature.startswith("0x")
        assert len(voucher.signature) == 132  # 0x + 65 bytes hex

    @pytest.mark.anyio
    async def test_cumulative_amounts(self):
        signer = LocalSigner(TEST_KEY)
        session = SessionClient(signer=signer, channel_id="0x" + "cd" * 32)
        v1 = await session.sign_voucher(5000)
        v2 = await session.sign_voucher(5000)
        v3 = await session.sign_voucher(10000)
        assert v1.cumulative_amount == 5000
        assert v2.cumulative_amount == 10000
        assert v3.cumulative_amount == 20000
        assert v1.nonce == 1
        assert v2.nonce == 2
        assert v3.nonce == 3


class TestSessionVerifier:
    @pytest.mark.anyio
    async def test_full_flow(self):
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "ef" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=100_000)

        v1 = await session.sign_voucher(5000)
        ok, delta, err = verifier.verify_voucher(v1)
        assert ok, f"verify failed: {err}"
        assert delta == 5000

        v2 = await session.sign_voucher(5000)
        ok, delta, err = verifier.verify_voucher(v2)
        assert ok, f"verify failed: {err}"
        assert delta == 5000

        result = verifier.close_channel(channel_id)
        assert result is not None
        assert result["total_spent"] == 10000
        assert result["refund"] == 90000

    @pytest.mark.anyio
    async def test_replay_rejected(self):
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "11" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=100_000)

        v1 = await session.sign_voucher(5000)
        ok, _, _ = verifier.verify_voucher(v1)
        assert ok
        ok, _, err = verifier.verify_voucher(v1)
        assert not ok
        assert "nonce" in err

    @pytest.mark.anyio
    async def test_exceeds_deposit(self):
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "22" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=5000)

        v1 = await session.sign_voucher(10000)
        ok, _, err = verifier.verify_voucher(v1)
        assert not ok
        assert "exceeds" in err

    @pytest.mark.anyio
    async def test_wrong_signer(self):
        other_key = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
        other_signer = LocalSigner(other_key)
        channel_id = "0x" + "33" * 32
        session = SessionClient(signer=other_signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=100_000)

        v = await session.sign_voucher(5000)
        ok, _, err = verifier.verify_voucher(v)
        assert not ok
        assert "mismatch" in err

    @pytest.mark.anyio
    async def test_top_up(self):
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "44" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=5000)

        # 先花完 deposit
        v1 = await session.sign_voucher(5000)
        ok, _, _ = verifier.verify_voucher(v1)
        assert ok

        # 超出 deposit
        v2 = await session.sign_voucher(5000)
        ok, _, err = verifier.verify_voucher(v2)
        assert not ok
        assert "exceeds" in err

        # Top up
        verifier.top_up(channel_id, 10000)

        # 现在可以了
        ok, delta, _ = verifier.verify_voucher(v2)
        assert ok
        assert delta == 5000

        result = verifier.close_channel(channel_id)
        assert result["total_spent"] == 10000
        assert result["refund"] == 5000  # 15000 - 10000
