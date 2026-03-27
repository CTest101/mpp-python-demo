# Test Report — MPP Python Demo

**Date**: 2026-03-27
**Platform**: Ubuntu 24.04 LTS, Python 3.14.3
**Chain**: Tempo Moderato Testnet (42431)
**pympp**: 0.4.2 | **pytempo**: 0.4.0

---

## Unit Tests: 31/31 passed ✅

```
tests/test_signer.py     — 9 tests (Signer abstraction)
tests/test_server.py     — 3 tests (FastAPI endpoints)
tests/test_session.py    — 7 tests (Session voucher sign/verify)
tests/test_benchmark.py  — 1 test  (Performance benchmark)
× 2 async backends (asyncio + trio) for async tests
```

### Signer Tests
| Test | Status |
|------|--------|
| `test_address` — LocalSigner returns correct checksummed address | ✅ |
| `test_is_signer` — LocalSigner is instance of Signer ABC | ✅ |
| `test_sign_hash` — async sign 32-byte hash → 65-byte sig | ✅ |
| `test_sign_hash_invalid_length` — reject non-32-byte input | ✅ |
| `test_to_tempo_account` — bridge to pympp TempoAccount | ✅ |
| `test_repr` — repr includes class name and address prefix | ✅ |
| `test_deterministic_signature` — same input → same output | ✅ |
| `test_missing_env` — signer_from_env raises on missing key | ✅ |
| `test_from_env` — signer_from_env loads from MPP_PRIVATE_KEY | ✅ |

### Server Tests
| Test | Status |
|------|--------|
| `test_root` — GET / returns service info + endpoints | ✅ |
| `test_joke_returns_402` — GET /joke without auth → 402 + WWW-Authenticate | ✅ |
| `test_gallery_returns_402` — GET /gallery/charge without auth → 402 | ✅ |

### Session Tests
| Test | Status |
|------|--------|
| `test_sign_voucher` — sign EIP-712 voucher, correct fields | ✅ |
| `test_cumulative_amounts` — amounts accumulate correctly | ✅ |
| `test_full_flow` — open → 2 vouchers → close, correct settlement | ✅ |
| `test_replay_rejected` — same voucher rejected (nonce check) | ✅ |
| `test_exceeds_deposit` — voucher > deposit rejected | ✅ |
| `test_wrong_signer` — ecrecover mismatch detected | ✅ |
| `test_top_up` — deposit追加后继续消费 | ✅ |

### Benchmark
| Metric | Value |
|--------|-------|
| Voucher sign (avg, 100 iterations) | **2.5 ms** |
| Voucher verify (avg, 100 iterations) | **3.7 ms** |
| Round-trip (sign + verify) | **6.2 ms** |
| vs Charge mode (~3s on-chain) | **~500x faster** |

---

## E2E Tests (Tempo Moderato Testnet)

### Test Account
- **Address**: `0x76BFc4B290823a08c6402fBC444A8E99B57d8a3D`
- **Funded via**: `tempo_fundAddress` RPC faucet
- **Token**: pathUSD on Moderato (42431)

### E2E 1: Charge — Local Server ✅
```
🔑 Signer: <LocalSigner 0x76BFc4B2...>
🔐 Signing via: LocalSigner (NOT pympp auto-sign)

💰 Charge mode — buying a joke (on-chain)...
  HTTP 200
🎭 Debugging: removing bugs. Programming: adding them.
💳 Payer: did:pkh:eip155:42431:0x76BFc4B290823a08c6402fBC444A8E99B57d8a3D
```

**Flow**: Client GET /joke → 402 challenge → SignerTempoMethod builds tx → `signer.sign_hash(get_signing_hash())` → submit to Tempo Moderato → server verifies receipt → 200 + joke

### E2E 2: Session — Local Server ✅
```
⚡ Session mode — buying 5 images (off-chain voucher)...
  📂 Opening session channel: 0xf7c99a238fe143f1...
  ✅ Channel opened: deposit $1.00
  [1] Forest Path | delta: $0.0050 | spent: $0.0050 | remaining: $0.9950
  [2] Ocean Breeze | delta: $0.0050 | spent: $0.0100 | remaining: $0.9900
  [3] Mountain Dawn | delta: $0.0050 | spent: $0.0150 | remaining: $0.9850
  [4] Mountain Dawn | delta: $0.0050 | spent: $0.0200 | remaining: $0.9800
  [5] City Lights | delta: $0.0050 | spent: $0.0250 | remaining: $0.9750
  ✅ Session closed: spent $0.0250, refund $0.9750
📊 Got 5 images (zero on-chain tx!)
```

**Flow**: POST /session/open → 5× (sign EIP-712 voucher → POST /session/gallery → ecrecover verify) → POST /session/close

### E2E 3: Official MPP Server (mpp.dev) ✅
```
🌐 Hitting official MPP test server: mpp.dev/api/ping/paid
  HTTP 200
  Body: tm! thanks for paying
  Receipt: {"method":"tempo","status":"success",
            "reference":"0x31bffa12e3aca4ce4e83115e4b0e63e4e55fd9cfd92623fab68fd0b64a846b81"}
```

**Flow**: Client GET mpp.dev/api/ping/paid → 402 challenge (realm="mpp.sh", feePayer=true) → SignerTempoMethod builds fee-payer envelope → Tempo fee payer sponsors gas → official server verifies → 200

---

## Test Coverage Summary

| Layer | Unit | E2E | Coverage |
|-------|------|-----|----------|
| Signer ABC | 9 tests | — | address, sign_hash, env, bridge |
| SignerTempoMethod | — | 2 E2E | charge via custom signer |
| Server (charge) | 3 tests | 2 E2E | 402 challenge, verify, receipt |
| Session (voucher) | 7 tests | 1 E2E | sign, verify, replay, deposit, top-up, close |
| Official server | — | 1 E2E | mpp.dev/api/ping/paid |
| Benchmark | 1 test | — | 100-iteration latency |

**Total: 31 unit tests + 3 E2E scenarios**
