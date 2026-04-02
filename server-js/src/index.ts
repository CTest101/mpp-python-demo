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

// ─── Logging ────────────────────────────────────────────────────────────────

function logRequest(req: Request): void {
  const url = new URL(req.url)
  const auth = req.headers.get('Authorization')
  if (!auth?.toLowerCase().startsWith('payment ')) return

  let action = '', source = '', channelId = '', cumAmount = ''
  try {
    const json = JSON.parse(atob(auth.slice(8)))
    action = json.payload?.action ?? ''
    source = json.source ?? ''
    channelId = json.payload?.channelId ? json.payload.channelId.slice(0, 18) + '...' : ''
    cumAmount = json.payload?.cumulativeAmount ?? ''
  } catch {}

  const parts = [`📥 ${req.method} ${url.pathname}`]
  if (action) parts.push(`action=${action}`)
  if (source) parts.push(`source=${source.length > 40 ? source.slice(0, 40) + '...' : source}`)
  if (channelId) parts.push(`ch=${channelId}`)
  if (cumAmount) parts.push(`cum=${cumAmount}`)
  console.log(parts.join(' '))
}

function logResponse(
  req: Request,
  status: number,
  startMs: number,
  extra?: Record<string, unknown>,
): void {
  const url = new URL(req.url)
  const ms = Date.now() - startMs
  const emoji = status === 200 || status === 204 ? '✅' : status === 402 ? '💳' : '❌'
  const parts = [`${emoji} ${req.method} ${url.pathname} ${status} ${ms}ms`]
  if (extra?.intent) parts.push(`intent=${extra.intent}`)
  if (extra?.action) parts.push(`action=${extra.action}`)
  if (extra?.image) parts.push(`image=${extra.image}`)
  if (extra?.payer) {
    const p = String(extra.payer)
    parts.push(`payer=${p.length > 40 ? p.slice(0, 40) + '...' : p}`)
  }
  if (extra?.error) parts.push(`error=${String(extra.error).slice(0, 80)}`)
  console.log(parts.join(' '))
}

function logError(context: string, error: unknown): void {
  console.error(`🔥 ${context}: ${error instanceof Error ? error.message : String(error)}`)
}

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

// ─── Stats ──────────────────────────────────────────────────────────────────

const stats = {
  startedAt: new Date().toISOString(),
  requests: 0,
  charge402: 0,
  charge200: 0,
  session402: 0,
  sessionOpen: 0,
  sessionVoucher: 0,
  sessionClose: 0,
  errors: 0,
}

// ─── Request Handler ────────────────────────────────────────────────────────

async function handler(request: Request): Promise<Response> {
  const startMs = Date.now()
  const url = new URL(request.url)
  stats.requests++

  // Free endpoints (no logging for health to reduce noise)
  if (url.pathname === '/') {
    return Response.json({
      service: 'MPP Demo Server (mppx)',
      version: '0.2.0',
      chain: 'Tempo Moderato Testnet (42431)',
      recipient: account.address,
      endpoints: {
        '/health': { mode: 'free' },
        '/joke': { mode: 'charge', price: '$0.01/request' },
        '/gallery': { mode: 'session', price: '$0.005/image' },
        '/stats': { mode: 'free', description: 'Server statistics' },
      },
      protocol: 'https://paymentauth.org',
    })
  }

  if (url.pathname === '/health') {
    return Response.json({ status: 'ok', recipient: account.address })
  }

  if (url.pathname === '/stats') {
    return Response.json({
      ...stats,
      uptime: `${((Date.now() - new Date(stats.startedAt).getTime()) / 1000).toFixed(0)}s`,
    })
  }

  // Charge endpoint: /joke ($0.01 per request)
  if (url.pathname === '/joke') {
    logRequest(request)
    try {
      const result = await mppx.charge({
        amount: '0.01',
        description: 'One programmer joke',
      })(request)

      if (result.status === 402) {
        stats.charge402++
        logResponse(request, 402, startMs, { intent: 'charge' })
        return result.challenge
      }

      // Verify we actually have a valid credential
      if (!result.credential) {
        stats.errors++
        logResponse(request, 500, startMs, { error: 'charge verified but no credential' })
        return Response.json(
          { error: 'Payment verification incomplete', detail: 'No credential in result' },
          { status: 500 },
        )
      }

      stats.charge200++
      const joke = randomChoice(JOKES)
      const payer = result.credential.source ?? 'unknown'
      logResponse(request, 200, startMs, {
        intent: 'charge',
        payer,
      })
      return result.withReceipt(
        Response.json({ joke, payer }),
      )
    } catch (e) {
      stats.errors++
      logError('/joke', e)
      logResponse(request, 500, startMs, { error: String(e) })
      return Response.json(
        { error: 'Internal error', detail: (e as Error).message },
        { status: 500 },
      )
    }
  }

  // Session endpoint: /gallery ($0.005 per image)
  if (url.pathname === '/gallery') {
    logRequest(request)
    try {
      const result = await mppx.session({
        amount: '0.005',
        unitType: 'image',
      })(request)

      if (result.status === 402) {
        stats.session402++
        logResponse(request, 402, startMs, { intent: 'session' })
        return result.challenge
      }

      // Determine action from credential payload for logging
      let action = 'unknown'
      try {
        const payload = result.credential?.payload as Record<string, unknown> | undefined
        action = (payload?.action as string) ?? 'unknown'
      } catch {}
      // Fallback: parse from Authorization header
      if (action === 'unknown') {
        try {
          const auth = request.headers.get('Authorization') ?? ''
          if (auth.toLowerCase().startsWith('payment ')) {
            const json = JSON.parse(atob(auth.slice(8)))
            action = json.payload?.action ?? 'unknown'
          }
        } catch {}
      }
      if (action === 'open') stats.sessionOpen++
      else if (action === 'voucher') stats.sessionVoucher++
      else if (action === 'close') stats.sessionClose++

      const image = randomChoice(GALLERY)
      const responseStatus = action === 'close' ? 204 : 200
      logResponse(request, responseStatus, startMs, {
        intent: 'session',
        action,
        image: action !== 'close' ? image.title : undefined,
      })

      return result.withReceipt(
        action === 'close'
          ? new Response(null, { status: 204 })
          : Response.json({ image }),
      )
    } catch (e) {
      stats.errors++
      logError('/gallery', e)
      const detail = (e as Error).message ?? String(e)
      logResponse(request, 402, startMs, { error: detail })
      return Response.json(
        {
          type: 'https://paymentauth.org/problems/verification-failed',
          title: 'Verification Failed',
          status: 402,
          detail,
        },
        { status: 402 },
      )
    }
  }

  logResponse(request, 404, startMs)
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
console.log(`   GET /gallery → session ($0.005/image)`)
console.log(`   GET /stats   → server statistics\n`)

Bun.serve({
  port: PORT,
  fetch: handler,
})
