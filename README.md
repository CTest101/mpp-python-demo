# MPP Python Demo

Machine Payments Protocol (MPP) demo — Python client + server implementing the [HTTP 402 Payment Authentication Scheme](https://paymentauth.org), with charge (per-request) and session (payment channel) intents.

Both Python and TypeScript (mppx) servers are included.

## Architecture

```
┌─────────────────┐                      ┌─────────────────┐
│   Python Client  │     HTTP 402          │   Server         │
│                  │   Payment Protocol    │   (Python/JS)    │
│  ┌────────────┐ │                      │                  │
│  │  Signer    │ │    GET /resource      │                  │
│  │  (ABC)     │ │    ← 402 + Challenge  │  HMAC challenge  │
│  └─────┬──────┘ │    → Authorization    │  → verify        │
│        │        │    ← 200 + Receipt    │  → 200 + receipt │
│  ┌─────┴──────┐ │                      │                  │
│  │ LocalSigner│ │  Charge: 每次链上 tx   │                  │
│  │ KmsSigner  │ │  Session: off-chain   │                  │
│  │ MpcSigner  │ │    voucher (~5ms)     │                  │
│  └────────────┘ │                      │                  │
└─────────────────┘                      └─────────────────┘
                           │
              Tempo Moderato Testnet (chain 42431)
```

## Two Payment Intents

Both use the same HTTP 402 protocol (`WWW-Authenticate: Payment` / `Authorization: Payment`), differing in `intent`:

### Charge (`intent="charge"`)
Each request = one on-chain transaction. Client signs a Tempo tx, server verifies on-chain.
- **Flow**: `GET → 402 → sign tx → Authorization: Payment → 200`
- **Latency**: ~2s (block confirmation)
- **Use case**: One-time purchases, low-frequency API

### Session (`intent="session"`)
Client opens an escrow payment channel, then sends EIP-712 cumulative vouchers — **zero chain calls** per request.
- **Flow**:
  ```
  GET /gallery → 402 + WWW-Authenticate: Payment intent="session"
  GET /gallery + Authorization: Payment {action:"open", tx, voucher} → 200 (server broadcasts open tx)
  GET /gallery + Authorization: Payment {action:"voucher", cumAmount} → 200 (~5ms, ecrecover only)
  GET /gallery + Authorization: Payment {action:"close"} → server settles on-chain
  ```
- **Latency**: ~5ms per request (after channel open)
- **Use case**: High-frequency API calls, per-token LLM metering

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
