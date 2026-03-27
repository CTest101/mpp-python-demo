"""Tests for the Signer abstraction layer."""

import pytest
from mpp_demo.signer import LocalSigner, Signer
from mpp.methods.tempo import TempoAccount

TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class TestLocalSigner:
    def test_address(self):
        signer = LocalSigner(TEST_KEY)
        assert signer.address == TEST_ADDRESS

    def test_is_signer(self):
        signer = LocalSigner(TEST_KEY)
        assert isinstance(signer, Signer)

    @pytest.mark.anyio
    async def test_sign_hash(self):
        signer = LocalSigner(TEST_KEY)
        msg_hash = b"\x00" * 32
        sig = await signer.sign_hash(msg_hash)
        assert len(sig) == 65

    @pytest.mark.anyio
    async def test_sign_hash_invalid_length(self):
        signer = LocalSigner(TEST_KEY)
        with pytest.raises(ValueError, match="32 bytes"):
            await signer.sign_hash(b"short")

    def test_to_tempo_account(self):
        signer = LocalSigner(TEST_KEY)
        account = signer.to_tempo_account()
        assert isinstance(account, TempoAccount)
        assert account.address == TEST_ADDRESS

    def test_repr(self):
        signer = LocalSigner(TEST_KEY)
        r = repr(signer)
        assert "LocalSigner" in r
        assert TEST_ADDRESS[:10] in r

    @pytest.mark.anyio
    async def test_deterministic_signature(self):
        signer = LocalSigner(TEST_KEY)
        msg_hash = b"\x01" * 32
        sig1 = await signer.sign_hash(msg_hash)
        sig2 = await signer.sign_hash(msg_hash)
        assert sig1 == sig2


class TestSignerFromEnv:
    def test_missing_env(self, monkeypatch):
        monkeypatch.delenv("MPP_PRIVATE_KEY", raising=False)
        from mpp_demo.signer import signer_from_env
        with pytest.raises(ValueError, match="MPP_PRIVATE_KEY"):
            signer_from_env()

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("MPP_PRIVATE_KEY", TEST_KEY)
        from mpp_demo.signer import signer_from_env
        signer = signer_from_env()
        assert signer.address == TEST_ADDRESS
