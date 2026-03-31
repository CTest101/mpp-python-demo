# MPP Python Demo

Machine Payments Protocol (MPP) demo — Python client + server with charge (on-chain) + session (HTTP 402 payment channel) + abstract signer.

Both Python and TypeScript (mppx) servers are included.

## Architecture

```
┌─────────────────┐                      ┌─────────────────┐
│   Python Client  │                      │   Server         │
│                  │    Charge (on-chain)  │   (Python/JS)    │
│  ┌────────────┐ │    GET /joke          │                  │
│  │  Signer    │←┼── sign_hash() ───────→│  402 challenge   │
│  │  (ABC)     │ │    → pay on Tempo     │  → verify tx     │
│  └─────┬──────┘ │    → 200 + receipt    │  → 200 + receipt │
│        │        │                      │                  │
│  ┌─────┴──────┐ │    Session (402)      │                  │
│  │ LocalSigner│ │    GET /gallery → 402 │  HMAC challenge  │
│  │ KmsSigner  │ │    open: sign tx ────→│  broadcast tx    │
│  │ MpcSigner  │ │    voucher: EIP-712──→│  ecrecover (~5ms)│
│  └────────────┘ │    close: ──────────→│  on-chain settle │
└─────────────────┘                      └─────────────────┘
                           │
              Tempo Moderato Testnet (chain 42431)
```

## Two Payment Modes

### Charge (On-chain)
Each request = one on-chain transaction via pympp SDK.
- **Latency**: ~2s (block confirmation)
- **Use case**: One-time purchases

### Session (HTTP 402 Protocol)
Client opens an escrow payment channel, sends EIP-712 cumulative vouchers. Server verifies via `ecrecover` — **zero chain calls** per request.
- **Latency**: ~5ms (CPU-bound ecrecover)
- **Protocol**: IETF Payment Authentication Scheme (`WWW-Authenticate: Payment`)
- **Use case**: High-frequency API calls, per-token LLM metering

```
GET /gallery → 402 + WWW-Authenticate: Payment intent="session"
GET /gallery + Authorization: Payment {action:"open", tx, voucher} → 200
GET /gallery + Authorization: Payment {action:"voucher", cumAmount} → 200 (~5ms)
GET /gallery + Authorization: Payment {action:"close"} → server settles on-chain
```

## Project Structure

```
mpp-python-demo/
├── src/mpp_demo/
│   ├── server.py              # Python server: charge (pympp) + session (402)
│   ├── client.py              # CLI: charge / gallery / session
│   ├── protocol.py            # Payment Auth: challenge/credential/receipt
│   ├── session.py             # EIP-712 voucher sign/verify
│   ├── session_http.py        # SessionHttpClient (402 protocol)
│   ├── onchain.py             # Tempo escrow contract client
│   ├── config.py              # Tempo Moderato Testnet config
│   └── signer/                # Abstract signer (LocalSigner, etc.)
├── server-js/                 # TypeScript server (mppx SDK + Bun)
│   └── src/index.ts
├── tests/                     # 31 tests
│   ├── test_signer.py
│   ├── test_server.py
│   ├── test_session.py
│   └── test_benchmark.py
└── docs/
    └── TEST_REPORT.md         # E2E detailed report with on-chain tx links
```

## Quick Start

### 1. Install

```bash
cd ~/codes/mpp-python-demo
uv sync --all-extras
```

### 2. Fund account

```bash
curl -X POST https://rpc.moderato.tempo.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tempo_fundAddress","params":["YOUR_ADDRESS"],"id":1}'
```

### 3. Start JS server (recommended)

```bash
cd server-js && bun install && bun run dev
```

### 4. Run client

```bash
export MPP_PRIVATE_KEY=0xYourPrivateKey

# Charge: buy a joke (on-chain, ~2s)
uv run python -m mpp_demo.client charge --server http://localhost:5555

# Session: buy images (402 protocol, ~5ms/image after open)
uv run python -m mpp_demo.client session --count 5 --server http://localhost:5555
```

## Servers

### TypeScript Server (mppx SDK)

Uses the official [mppx](https://github.com/wevm/mppx) SDK. Both charge and session modes via `tempo()`.

```bash
cd server-js && bun run dev  # port 5555
```

### Python Server (FastAPI)

Custom 402 protocol implementation. Charge via pympp SDK, session via `protocol.py`.

```bash
MPP_RECIPIENT=0x... MPP_SERVER_PRIVATE_KEY=0x... \
  uv run uvicorn mpp_demo.server:app --port 5555
```

## Endpoints

| Endpoint | Mode | Price |
|----------|------|-------|
| `GET /health` | free | — |
| `GET /joke` | charge | $0.01/request |
| `GET /gallery/charge` | charge | $0.005/image |
| `GET /gallery` | session (402) | $0.005/image |

## Signer Abstraction

```
Signer (ABC)
├── sign_hash(bytes32) → bytes65
├── address → str
│
├── LocalSigner        ← private key (dev/testing)
├── KmsSigner          ← AWS/GCP KMS (TODO)
└── MpcSigner          ← Cobo TSS / Fireblocks (TODO)
```

## Tech Stack

- **Python** 3.12+ / **Bun** 1.3+
- **pympp** 0.5.0 / **mppx** 0.5.0
- **pytempo** 0.4.0 / **viem** 2.47
- **Chain**: Tempo Moderato Testnet (42431)
- **Token**: pathUSD (6 decimals)

## Tests

```bash
uv run pytest tests/ -v  # 31 passed
```
