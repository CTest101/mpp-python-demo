# MPP Demo Server (TypeScript / mppx)

TypeScript server using the official [mppx](https://github.com/wevm/mppx) SDK.

## Endpoints

| Endpoint      | Mode    | Price          |
|---------------|---------|----------------|
| `GET /`       | free    | —              |
| `GET /health` | free    | —              |
| `GET /joke`   | charge  | $0.01/request  |
| `GET /gallery`| session | $0.005/image   |

## Quick Start

```bash
cd server-js
bun install
bun run dev
```

Server listens on `http://localhost:5555` by default.

## Environment Variables

| Variable       | Default                              | Description            |
|----------------|--------------------------------------|------------------------|
| `PORT`         | `5555`                               | Server port            |
| `PRIVATE_KEY`  | _(auto-generated)_                   | Server private key     |
| `MPPX_RPC_URL` | _(SDK default)_                      | Tempo RPC URL          |
| `MPP_SECRET_KEY`| `demo-secret-key-change-in-production` | HMAC secret for challenges |

## Protocol

- **Charge** (`/joke`): Standard HTTP 402 → client signs on-chain tx → server verifies
- **Session** (`/gallery`): HTTP 402 → client opens escrow channel → sends cumulative vouchers → server closes on-chain

Both use the `WWW-Authenticate: Payment` scheme per [paymentauth.org](https://paymentauth.org).
