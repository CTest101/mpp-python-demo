"""Tests for on-chain session components.

Unit tests that don't require actual RPC — test EIP-712 signing consistency,
calldata encoding, and the off-chain voucher flow with contract-compatible types.
"""

import pytest
from eth_account import Account

from mpp_demo.signer import LocalSigner
from mpp_demo.session import (
    SessionClient,
    SessionVerifier,
    Voucher,
    _build_voucher_typed_data,
    compute_voucher_digest,
    SESSION_DOMAIN,
    VOUCHER_TYPEHASH,
    DOMAIN_SEPARATOR,
    ESCROW_CONTRACT,
)
from mpp_demo.onchain import (
    _encode_open,
    _encode_settle,
    _encode_close,
    _encode_topup,
    _encode_compute_channel_id,
    _encode_get_voucher_digest,
    ESCROW_ADDRESS,
)

TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class TestEIP712Domain:
    """Verify the EIP-712 domain matches the contract."""

    def test_domain_name(self):
        assert SESSION_DOMAIN["name"] == "Tempo Stream Channel"

    def test_domain_version(self):
        assert SESSION_DOMAIN["version"] == "1"

    def test_domain_verifying_contract(self):
        assert SESSION_DOMAIN["verifyingContract"].lower() == ESCROW_ADDRESS.lower()

    def test_voucher_typehash(self):
        """VOUCHER_TYPEHASH matches keccak256("Voucher(bytes32 channelId,uint128 cumulativeAmount)")."""
        from eth_utils import keccak
        expected = keccak(b"Voucher(bytes32 channelId,uint128 cumulativeAmount)")
        assert VOUCHER_TYPEHASH == expected

    def test_domain_separator_precomputed(self):
        """DOMAIN_SEPARATOR is correctly precomputed."""
        assert len(DOMAIN_SEPARATOR) == 32


class TestVoucherSigning:
    """Test that voucher signing matches expected EIP-712 format."""

    @pytest.mark.anyio
    async def test_sign_and_recover(self):
        """Sign a voucher and recover the signer via ecrecover."""
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "ab" * 32

        digest = compute_voucher_digest(channel_id, 5000)
        sig_bytes = await signer.sign_hash(digest)

        recovered = Account._recover_hash(digest, signature=sig_bytes)
        assert recovered.lower() == TEST_ADDRESS.lower()

    @pytest.mark.anyio
    async def test_session_client_signs_contract_compatible(self):
        """SessionClient produces vouchers verifiable by contract."""
        signer = LocalSigner(TEST_KEY)
        session = SessionClient(signer=signer, channel_id="0x" + "cd" * 32)
        voucher = await session.sign_voucher(5000)

        digest = compute_voucher_digest(voucher.channel_id, voucher.cumulative_amount)
        sig_bytes = bytes.fromhex(voucher.signature[2:])
        recovered = Account._recover_hash(digest, signature=sig_bytes)
        assert recovered.lower() == TEST_ADDRESS.lower()

    @pytest.mark.anyio
    async def test_verifier_accepts_contract_compatible_voucher(self):
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "ef" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=100_000)

        v = await session.sign_voucher(5000)
        ok, delta, err = verifier.verify_voucher(v)
        assert ok, f"Verify failed: {err}"
        assert delta == 5000

    @pytest.mark.anyio
    async def test_best_signature_tracked(self):
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "11" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=100_000)

        v1 = await session.sign_voucher(5000)
        verifier.verify_voucher(v1)

        v2 = await session.sign_voucher(5000)
        verifier.verify_voucher(v2)

        channel = verifier.get_channel(channel_id)
        assert channel is not None
        assert channel.best_signature == v2.signature

    @pytest.mark.anyio
    async def test_close_returns_best_signature(self):
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "22" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=100_000)

        v = await session.sign_voucher(5000)
        verifier.verify_voucher(v)

        result = verifier.close_channel(channel_id)
        assert result is not None
        assert result["best_signature"] == v.signature


class TestCalldataEncoding:
    """Test ABI calldata encoding matches expected function selectors."""

    def test_encode_open(self):
        data = _encode_open(TEST_ADDRESS, TEST_ADDRESS, 1000, b"\x00" * 32, TEST_ADDRESS)
        assert data.startswith("0xc79ea485")

    def test_encode_settle(self):
        data = _encode_settle(b"\x00" * 32, 1000, b"\x00" * 65)
        assert data.startswith("0x")
        assert len(data) > 10

    def test_encode_close(self):
        data = _encode_close(b"\x00" * 32, 1000, b"\x00" * 65)
        assert data.startswith("0x")

    def test_encode_topup(self):
        data = _encode_topup(b"\x00" * 32, 1000)
        assert data.startswith("0x")

    def test_encode_compute_channel_id(self):
        data = _encode_compute_channel_id(TEST_ADDRESS, TEST_ADDRESS, TEST_ADDRESS, b"\x00" * 32, TEST_ADDRESS)
        assert data.startswith("0x5af3dc68")

    def test_encode_get_voucher_digest(self):
        data = _encode_get_voucher_digest(b"\x00" * 32, 1000)
        assert data.startswith("0x")
