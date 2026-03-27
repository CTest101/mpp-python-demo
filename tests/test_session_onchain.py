"""Tests for on-chain session components.

Unit tests that don't require actual RPC — test EIP-712 signing consistency,
calldata encoding, and the off-chain voucher flow with contract-compatible types.
"""

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from mpp_demo.signer import LocalSigner
from mpp_demo.session import (
    SessionClient,
    SessionVerifier,
    Voucher,
    _build_voucher_typed_data,
    SESSION_DOMAIN,
    VOUCHER_TYPES,
    EIP712_DOMAIN_TYPE,
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

    def test_voucher_type_no_nonce(self):
        """Voucher type should only have channelId + cumulativeAmount (no nonce)."""
        fields = VOUCHER_TYPES["Voucher"]
        field_names = [f["name"] for f in fields]
        assert "channelId" in field_names
        assert "cumulativeAmount" in field_names
        assert "nonce" not in field_names
        assert len(fields) == 2

    def test_cumulative_amount_is_uint128(self):
        """Contract uses uint128 for cumulativeAmount."""
        fields = VOUCHER_TYPES["Voucher"]
        amount_field = next(f for f in fields if f["name"] == "cumulativeAmount")
        assert amount_field["type"] == "uint128"


class TestVoucherSigning:
    """Test that voucher signing matches expected EIP-712 format."""

    @pytest.mark.anyio
    async def test_sign_and_recover(self):
        """Sign a voucher and recover the signer via ecrecover."""
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "ab" * 32

        # Sign
        typed_data = _build_voucher_typed_data(channel_id, 5000)
        signable = encode_typed_data(full_message=typed_data)
        sig_bytes = await signer.sign_hash(signable.body)

        # Recover
        recovered = Account._recover_hash(signable.body, signature=sig_bytes)
        assert recovered.lower() == TEST_ADDRESS.lower()

    @pytest.mark.anyio
    async def test_session_client_signs_contract_compatible(self):
        """SessionClient produces vouchers that match the contract EIP-712."""
        signer = LocalSigner(TEST_KEY)
        session = SessionClient(signer=signer, channel_id="0x" + "cd" * 32)
        voucher = await session.sign_voucher(5000)

        # Manually reconstruct the typed data and verify
        typed_data = _build_voucher_typed_data(voucher.channel_id, voucher.cumulative_amount)
        signable = encode_typed_data(full_message=typed_data)
        sig_bytes = bytes.fromhex(voucher.signature[2:])
        recovered = Account._recover_hash(signable.body, signature=sig_bytes)
        assert recovered.lower() == TEST_ADDRESS.lower()

    @pytest.mark.anyio
    async def test_verifier_accepts_contract_compatible_voucher(self):
        """SessionVerifier correctly verifies contract-compatible vouchers."""
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
        """Verifier tracks the best (latest) voucher signature for on-chain close."""
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "99" * 32
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
        """close_channel returns the best signature for on-chain settlement."""
        signer = LocalSigner(TEST_KEY)
        channel_id = "0x" + "88" * 32
        session = SessionClient(signer=signer, channel_id=channel_id)
        verifier = SessionVerifier()
        verifier.open_channel(channel_id, TEST_ADDRESS, deposit=100_000)

        v = await session.sign_voucher(5000)
        verifier.verify_voucher(v)

        result = verifier.close_channel(channel_id)
        assert result is not None
        assert result["best_signature"] == v.signature
        assert result["total_spent"] == 5000


class TestCalldataEncoding:
    """Test ABI encoding for escrow contract calls."""

    def test_encode_open(self):
        payee = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
        token = "0x20c0000000000000000000000000000000000000"
        data = _encode_open(payee, token, 1_000_000, b"\x00" * 32, "0x" + "00" * 20)
        assert data.startswith("0x")
        assert len(data) > 10  # selector + encoded args

    def test_encode_settle(self):
        channel_id = b"\xab" * 32
        sig = b"\x00" * 65
        data = _encode_settle(channel_id, 5000, sig)
        assert data.startswith("0x")

    def test_encode_close(self):
        channel_id = b"\xcd" * 32
        sig = b"\x00" * 65
        data = _encode_close(channel_id, 5000, sig)
        assert data.startswith("0x")

    def test_encode_topup(self):
        channel_id = b"\xef" * 32
        data = _encode_topup(channel_id, 500_000)
        assert data.startswith("0x")

    def test_encode_compute_channel_id(self):
        data = _encode_compute_channel_id(
            TEST_ADDRESS,
            "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            "0x20c0000000000000000000000000000000000000",
            b"\x00" * 32,
            "0x" + "00" * 20,
        )
        assert data.startswith("0x")

    def test_encode_get_voucher_digest(self):
        channel_id = b"\xab" * 32
        data = _encode_get_voucher_digest(channel_id, 5000)
        assert data.startswith("0x")
