# MPP Python Demo

Machine Payments Protocol (MPP) demo — Python implementation with charge (on-chain) + session (off-chain voucher) + abstract signer.

## Architecture

```
┌─────────────────┐                      ┌─────────────────┐
│   MPP Client     │                      │   MPP Server     │
│                  │                      │   (FastAPI)      │
│  ┌────────────┐ │    Charge (on-chain)  │                  │
│  │  Signer    │←┼── sign_hash() ───────→│  Mpp.charge()    │
│  │  (ABC)     │ │    GET /joke          │  → 402 challenge │
│  └─────┬──────┘ │    → pay on Tempo     │  → verify tx     │
│        │        │    → 200 + receipt    │  → 200 + receipt │
│  ┌─────┴──────┐ │                      │                  │
│  │ LocalSigner│ │    Session (off-chain)│                  │
│  │ KmsSigner  │ │    POST /session/open │  SessionVerifier │
│  │ MpcSigner  │ │    POST /session/xxx  │  → ecrecover     │
│  └────────────┘ │    → EIP-712 voucher  │  → zero RPC      │
│                  │    POST /session/close│  → batch settle  │
└─────────────────┘                      └─────────────────┘
                           │
              Tempo Moderato Testnet (chain 42431)
```

## Two Payment Modes

### Charge (On-chain)
Each request = one on-chain transaction. Server verifies by checking Tempo Testnet.
- **Latency**: ~2-4s (block confirmation)
- **Cost**: Gas fee per request
- **Use case**: One-time purchases, high-value transactions

### Session (Off-chain Voucher)
Client opens a payment channel, signs EIP-712 cumulative vouchers. Server verifies with `ecrecover` — **zero chain calls**.
- **Latency**: ~microseconds (CPU-bound `ecrecover`)
- **Cost**: Near zero (batch settle on close)
- **Use case**: High-frequency API billing, per-token LLM metering

## Signer Abstraction

```
Signer (ABC)
├── sign_hash(bytes32) → bytes65
├── address → str
│
├── LocalSigner        ← private key (dev/testing)
├── KmsSigner          ← AWS/GCP KMS (TODO)
├── MpcSigner          ← Cobo TSS / Fireblocks (TODO)
└── PasskeySigner      ← WebAuthn (TODO)
```

The `Signer` base class provides a single `sign_hash()` method. `SignerTempoMethod` overrides pympp's internal signing flow:

```
pympp default:   tx.sign(private_key)         ← SDK controls signing
our approach:    tx.get_signing_hash() → 32 bytes
                 signer.sign_hash(hash) → 65 bytes  ← WE control signing
                 attrs.evolve(tx, signature=sig)
```

## Project Structure

```
mpp-python-demo/
├── pyproject.toml
├── README.md
├── src/mpp_demo/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py                  # Tempo Moderato Testnet config
│   ├── server.py                  # FastAPI: charge + session endpoints
│   ├── client.py                  # CLI: charge / gallery / session
│   ├── session.py                 # Session: EIP-712 voucher sign/verify
│   └── signer/
│       ├── __init__.py
│       ├── base.py                # Signer ABC
│       ├── local.py               # LocalSigner (private key)
│       ├── env.py                 # signer_from_env() factory
│       └── tempo_adapter.py       # SignerTempoMethod (override pympp signing)
└── tests/
    ├── test_signer.py             # 9 tests
    ├── test_server.py             # 3 tests
    └── test_session.py            # 6 tests
```

## Quick Start

```bash
# 1. Install
cd ~/codes/mpp-python-demo
uv sync --all-extras

# 2. Get testnet tokens (via RPC faucet)
curl -X POST https://rpc.moderato.tempo.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tempo_fundAddress","params":["YOUR_ADDRESS"],"id":1}'

# 3. Start server
export MPP_RECIPIENT=0xYourAddress
export MPP_SECRET_KEY=your-secret-key
uv run uvicorn mpp_demo.server:app --port 8000

# 4. Run client
export MPP_PRIVATE_KEY=0xYourPrivateKey

# Charge: buy a joke (on-chain, ~3s)
uv run python -m mpp_demo.client charge

# Session: buy 5 images (off-chain voucher, ~instant)
uv run python -m mpp_demo.client session --count 5

# Gallery: buy images (on-chain charge per image)
uv run python -m mpp_demo.client gallery --count 3
```

## Endpoints

| Endpoint | Mode | Price | Description |
|----------|------|-------|-------------|
| `GET /joke` | charge | $0.01 | Programmer joke (on-chain) |
| `GET /gallery/charge` | charge | $0.005 | Random image (on-chain) |
| `POST /session/open` | session | — | Open payment channel |
| `POST /session/gallery` | session | $0.005 | Image via voucher (off-chain) |
| `POST /session/close` | session | — | Settle & refund |

## E2E Test Results

### Charge (on-chain, Signer-controlled signing)
```
🔑 Signer: <LocalSigner 0x76BFc4B2...>
🔐 Signing via: LocalSigner (NOT pympp auto-sign)
💰 Charge mode — buying a joke (on-chain)...
  HTTP 200
🎭 Debugging: removing bugs. Programming: adding them.
💳 Payer: did:pkh:eip155:42431:0x76BFc4B2...
```

### Session (off-chain voucher, zero chain calls)
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

## Comparison: MPP vs x402

| Aspect | MPP (this demo) | x402 (x402-local-lab) |
|--------|-----------------|----------------------|
| **Signer** | `Signer` ABC → `sign_hash(bytes32)` | `X402Signer` → `signHash(hex)` |
| **Payment modes** | Charge (on-chain) + Session (off-chain) | Charge only (every request on-chain) |
| **Per-request cost** | Session: ~$0 / Charge: gas | Every request: gas |
| **Verification latency** | Session: µs / Charge: ~3s | ~block time per request |
| **Protocol** | HTTP 402 + IETF spec | HTTP 402 (no spec) |
| **Server SDK** | `pympp` + `Mpp.create()` | `@x402/server` middleware |
| **Chain** | Tempo Moderato (42431) | Base Sepolia / Solana Devnet |
| **Session support** | ✅ EIP-712 vouchers | ❌ |
| **MCP transport** | ✅ (spec defined) | ❌ |
| **IETF standardization** | ✅ paymentauth.org | ❌ |
| **Multi-method** | ✅ Tempo + Stripe + Lightning | ❌ Blockchain only |

### Key Architectural Difference
x402's signer abstraction is thin (just `signHash` + `signTypedData`), but every payment requires a full on-chain transaction.

MPP's session mode eliminates on-chain calls during service consumption — the client signs cumulative EIP-712 vouchers, the server verifies with `ecrecover` in microseconds, and settlement happens in batches on channel close.

## Tech Stack

- **Python** 3.12+
- **Server**: FastAPI + pympp 0.4.2 (official SDK)
- **Client**: pympp Client + SignerTempoMethod
- **Session**: EIP-712 typed data + eth-account
- **Chain**: Tempo Moderato Testnet (42431)
- **Token**: pathUSD (`0x20c0...`)
- **Package manager**: uv

## Tests

```bash
uv run pytest tests/ -v
# 18 passed ✅
```
