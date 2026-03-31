/**
 * MPP Demo Server (TypeScript / Bun)
 *
 * Supports both charge and session payment modes using mppx SDK.
 *
 * Endpoints:
 *   GET  /              — Service info (free)
 *   GET  /health        — Health check (free)
 *   GET  /joke          — Paid joke (charge, $0.01/request)
 *   GET  /gallery       — Paid gallery image (session, $0.005/image)
 *
 * Usage:
 *   bun run src/index.ts
 *
 * Environment:
 *   PORT              — Server port (default: 5555)
 *   MPPX_RPC_URL      — Tempo RPC URL (optional, SDK has defaults)
 *   PRIVATE_KEY        — Server private key (optional, generates fresh key if unset)
 */

import { Mppx, tempo } from 'mppx/server'
import { createClient, http, type Hex } from 'viem'
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts'
import { tempoModerato } from 'viem/chains'
import { Actions } from 'viem/tempo'

// ─── Config ─────────────────────────────────────────────────────────────────

const PORT = parseInt(process.env.PORT ?? '5555', 10)
const currency = '0x20c0000000000000000000000000000000000000' as const // pathUSD

// Server account — signs close/settle txs and receives payments
const account = privateKeyToAccount(
  (process.env.PRIVATE_KEY as Hex) ?? generatePrivateKey(),
)

// viem client with account attached (needed for on-chain session operations)
const client = createClient({
  account,
  chain: tempoModerato,
  pollingInterval: 1_000,
  transport: http(process.env.MPPX_RPC_URL),
})

// ─── Payment Handler ────────────────────────────────────────────────────────

// tempo() returns both charge and session methods when given an account
const mppx = Mppx.create({
  secretKey: process.env.MPP_SECRET_KEY ?? 'demo-secret-key-change-in-production',
  methods: [
    ...tempo({
      account,        // Account object (not just address) — needed for session close/settle
      currency,
      feePayer: process.env.FEE_PAYER === 'false' ? false : true,
      testnet: true,
      getClient: () => client,
    }),
  ],
})

// ─── Data ───────────────────────────────────────────────────────────────────

const JOKES = [
  "Why do programmers prefer dark mode? Because light attracts bugs. 🪲",
  "There are 10 types of people: those who understand binary, and those who don't.",
  "A SQL query walks into a bar, sees two tables, and asks: 'Can I JOIN you?'",
  "!false — it's funny because it's true.",
  "A programmer's wife tells him: 'Go buy a loaf of bread. If they have eggs, get a dozen.' He comes home with 12 loaves. 🍞",
  "Why do Java developers wear glasses? Because they don't C#.",
  "Debugging: removing bugs. Programming: adding them.",
]

const GALLERY = [
  { id: 1, url: 'https://picsum.photos/400/300?random=1', title: 'Mountain Dawn' },
  { id: 2, url: 'https://picsum.photos/400/300?random=2', title: 'Ocean Breeze' },
  { id: 3, url: 'https://picsum.photos/400/300?random=3', title: 'City Lights' },
  { id: 4, url: 'https://picsum.photos/400/300?random=4', title: 'Forest Path' },
  { id: 5, url: 'https://picsum.photos/400/300?random=5', title: 'Desert Sun' },
]

function randomChoice<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]!
}

// ─── Request Handler ────────────────────────────────────────────────────────

async function handler(request: Request): Promise<Response> {
  const url = new URL(request.url)

  // Free endpoints
  if (url.pathname === '/') {
    return Response.json({
      service: 'MPP Demo Server (mppx)',
      version: '0.1.0',
      chain: 'Tempo Moderato Testnet (42431)',
      recipient: account.address,
      endpoints: {
        '/health': { mode: 'free' },
        '/joke': { mode: 'charge', price: '$0.01/request' },
        '/gallery': { mode: 'session', price: '$0.005/image' },
      },
      protocol: 'https://paymentauth.org',
    })
  }

  if (url.pathname === '/health') {
    return Response.json({ status: 'ok', recipient: account.address })
  }

  // Charge endpoint: /joke ($0.01 per request)
  if (url.pathname === '/joke') {
    const result = await mppx.charge({
      amount: '0.01',
      description: 'One programmer joke',
    })(request)

    if (result.status === 402) return result.challenge

    return result.withReceipt(
      Response.json({
        joke: randomChoice(JOKES),
        payer: result.credential.source,
      }),
    )
  }

  // Session endpoint: /gallery ($0.005 per image)
  if (url.pathname === '/gallery') {
    const result = await mppx.session({
      amount: '0.005',
      unitType: 'image',
    })(request)

    if (result.status === 402) return result.challenge

    return result.withReceipt(
      Response.json({
        image: randomChoice(GALLERY),
      }),
    )
  }

  return Response.json({ error: 'not_found' }, { status: 404 })
}

// ─── Startup ────────────────────────────────────────────────────────────────

console.log(`🔑 Server recipient: ${account.address}`)
console.log('💰 Funding server account via faucet...')

try {
  await Actions.faucet.fundSync(client, { account, timeout: 30_000 })
  console.log('✅ Server account funded')
} catch (e) {
  console.warn('⚠️  Faucet funding failed (may already have funds):', (e as Error).message)
}

console.log(`\n🚀 MPP Demo Server (mppx) listening on http://localhost:${PORT}`)
console.log(`   GET /joke    → charge ($0.01)`)
console.log(`   GET /gallery → session ($0.005/image)\n`)

Bun.serve({
  port: PORT,
  fetch: handler,
})
