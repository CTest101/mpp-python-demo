# MPP Services Directory

> Auto-generated from <https://mpp.dev/api/services> — 83 services
> All services use HTTP 402 Payment Authentication Scheme
> Discovery API: `GET https://mpp.dev/api/services` | Agent docs: <https://mpp.dev/services/llms.txt>

## Network & Currency

| Network | Chain ID | Currency | Address | Decimals | Method |
|---------|----------|----------|---------|----------|--------|
| **Tempo Mainnet** | 4217 | USDC | `0x20c000000000000000000000b9537d11c60e8b50` | 6 | tempo |
| **Tempo Testnet** (Moderato) | 42431 | pathUSD | `0x20c0000000000000000000000000000000000000` | 6 | tempo |
| **Stripe** (fiat) | — | USD | — | 2 | stripe |

- **80 services** use Tempo method with USDC on mainnet (chainId 4217)
- **3 services** use Stripe method with USD (Prospect Butcher, Tako, Stripe Climate)
- **Testnet (42431)** is only used by self-hosted demo servers, not production services
- Session escrow: `0x33b901018174DDabE4841042ab76ba85D4e24f25` (mainnet) / `0xe1c4d3dce17bc111181ddf716f75bae49e61a336` (testnet)

## Session Services (9)

Payment channel — open once, pay per request with off-chain vouchers (~5ms). All on **Tempo Mainnet (4217) USDC**.

| Service | URL | Intents | Category |
|---------|-----|---------|----------|
| **Alchemy** | `https://mpp.alchemy.com` | session | blockchain, data |
| **Anthropic** | `https://anthropic.mpp.tempo.xyz` | session | ai |
| **Dune** | `https://api.dune.com` | session | data, blockchain |
| **Google Gemini** | `https://gemini.mpp.tempo.xyz` | session | ai, media |
| **Modal** | `https://modal.mpp.tempo.xyz` | session | compute |
| **Object Storage** | `https://storage.mpp.tempo.xyz` | charge+session | storage |
| **OpenAI** | `https://openai.mpp.tempo.xyz` | charge+session | ai, media |
| **OpenRouter** | `https://openrouter.mpp.tempo.xyz` | session | ai |
| **Tempo RPC** | `https://rpc.mpp.tempo.xyz` | session | blockchain |

### Alchemy
> Blockchain data APIs including Core RPC APIs, Prices API, Portfolio API, and NFT API across 100+ chains.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/:network/v2` | session | $0.0001 | JSON-RPC call (eth_*, alchemy_*) |
| GET | `/:network/nft/v3/:endpoint` | session | $0.0005 | NFT API v3 |
| POST | `/:network/nft/v3/:endpoint` | session | $0.0005 | NFT API v3 |

### Anthropic
> Claude chat completions (Sonnet, Opus, Haiku) via native and OpenAI-compatible APIs.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/v1/messages` | session | dynamic | Create messages with Claude (Sonnet, Opus, Haiku) - price varies by model |
| POST | `/v1/chat/completions` | session | dynamic | OpenAI-compatible chat completions (auto-converted to Anthropic format) |

### Dune
> Query across raw transaction data, decoded smart contract events, stablecoin flows, RWA tracking, protocol analytics, DeFi positions, NFT activity, blockchain market research, and whatever is trending in crypto.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/api/v1/sql/execute` | session | $0.05-$4 | Execute a SQL query |
| GET | `/api/v1/execution/:execution_id/csv` | session | $0.05-$10 | Download CSV results for an execution |
| GET | `/api/v1/execution/:execution_id/results` | session | $0.05-$10 | Fetch JSON results for an execution |

### Google Gemini
> Gemini text generation, Veo video, and Nano Banana image generation with model-tier pricing.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/:version/models/*` | session | $0.0005 | Generate content (Gemini, Veo, Imagen, etc.) - price varies by model |
| GET | `/:version/operations/*` | session | $0.0001 | Poll async operation status |
| POST | `/:version/files` | session | $0.0010 | Upload file for multimodal input |
| GET | `/:version/models` |  | free | List available models (free) |
| GET | `/:version/models/*` |  | free | Get model details (free) |
| GET | `/:version/files` |  | free | List uploaded files (free) |
| GET | `/:version/files/*` |  | free | Get file details (free) |
| DELETE | `/:version/files/*` |  | free | Delete an uploaded file (free) |
| GET | `/:version/cachedContents` |  | free | List cached contents (free) |
| GET | `/:version/cachedContents/*` |  | free | Get cached content details (free) |

### Modal
> Serverless GPU compute for sandboxed code execution and AI/ML workloads.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/sandbox/create` | session | dynamic | Create a sandbox for code execution |
| POST | `/sandbox/exec` | session | $0.0001 | Execute command in sandbox |
| POST | `/sandbox/status` | session | $0.0001 | Get sandbox status |
| POST | `/sandbox/terminate` | session | $0.0001 | Terminate a sandbox |

### Object Storage
> S3/R2-compatible object storage with dynamic per-size pricing.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| GET | `/:key` | session | dynamic | Download object ($0.001 base + $0.01/MB) |
| PUT | `/:key` | session | dynamic | Upload object ($0.001 base + $0.01/MB, max 100MB) |
| DELETE | `/:key` | charge | $0.0001 | Delete object |
| GET | `/` | charge | $0.0001 | List objects |
| POST | `/:key` | charge | $0.0001 | Initiate/complete multipart upload |

### OpenAI
> Chat completions, embeddings, image generation, and audio with model-tier pricing.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/v1/responses` | session | dynamic | Responses API (Codex, GPT-4o, etc.) - price varies by model |
| POST | `/v1/chat/completions` | session | dynamic | Chat completions (GPT-4o, GPT-4, o1, etc.) - price varies by model |
| POST | `/v1/embeddings` | charge | $0.0001 | Create embeddings |
| POST | `/v1/images/generations` | charge | $0.0500 | Generate images with DALL-E |
| POST | `/v1/audio/transcriptions` | charge | $0.0100 | Transcribe audio with Whisper |
| POST | `/v1/audio/speech` | charge | $0.0200 | Text-to-speech |

### OpenRouter
> Unified API for 100+ LLMs with live per-model pricing.

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/v1/chat/completions` | session | dynamic | Chat completions (GPT-4, Claude, Llama, etc.) - price varies by model |

### Tempo RPC
> Tempo blockchain JSON-RPC access (mainnet and testnet).

| Method | Path | Intent | Price | Description |
|--------|------|--------|-------|-------------|
| POST | `/` | session | $0.0010 | JSON-RPC calls - $0.001 per call |

## Charge Services (71)

One-time payment per request. All on **Tempo Mainnet (4217) USDC** unless noted.

| Service | URL | Category | Description |
|---------|-----|----------|-------------|
| **2Captcha** | `https://twocaptcha.mpp.tempo.xyz` | web | CAPTCHA solving API — reCAPTCHA, Turnstile, hCaptcha, image captchas, and more. |
| **AgentMail** | `https://mpp.api.agentmail.to` | ai, social | Email inboxes for AI agents. |
| **Allium** | `https://agents.allium.so` | blockchain, data | System of record for onchain finance. Real-time blockchain data: token prices, w... |
| **Alpha Vantage** | `https://alphavantage.mpp.paywithlocus.com` | data | Financial market data — stock prices, forex, crypto, commodities, economic indic... |
| **Apollo** | `https://apollo.mpp.paywithlocus.com` | data | People and company enrichment, lead search, and sales intelligence with 275M+ co... |
| **AviationStack** | `https://aviationstack.mpp.tempo.xyz` | data | Real-time and historical flight tracking, airports, airlines, and schedules. |
| **Billboard** | `https://billboard.mpp.paywithlocus.com` | data | Post to @MPPBillboard on X. Price starts at $0.01 and doubles with every post. T... |
| **Brave Search** | `https://brave.mpp.paywithlocus.com` | search | Independent web search — web, news, images, videos, AI answers, and LLM context.... |
| **Browserbase** | `https://mpp.browserbase.com` | web, compute, search | Headless browser sessions, web search, and page fetching for AI agents. |
| **Build With Locus** | `https://mpp.buildwithlocus.com` | compute | Deploy containerized services, Postgres, Redis, and custom domains on demand — a... |
| **BuiltWith** | `https://builtwith.mpp.paywithlocus.com` | data | Technology profiling for websites — detect tech stacks, find sites using specifi... |
| **Clado** | `https://clado.mpp.paywithlocus.com` | data | People search, LinkedIn enrichment, and deep research for lead generation. |
| **Code Storage** | `https://codestorage.mpp.tempo.xyz` | storage | Paid Git repository creation — create repos and get authenticated clone URLs. |
| **Codex** | `https://graph.codex.io` | blockchain, data | Comprehensive onchain data API for tokens and prediction markets. Real-time pric... |
| **CoinGecko** | `https://coingecko.mpp.paywithlocus.com` | data | Cryptocurrency market data — prices, charts, market cap, exchanges, trending coi... |
| **Company Enrichment** | `https://abstract-company-enrichment.mpp.paywithlocus.com` | data | Enrich company data from a domain name. |
| **Deepgram** | `https://deepgram.mpp.paywithlocus.com` | data | Industry-leading speech AI — transcribe audio from URLs with Nova-3, generate na... |
| **DeepL** | `https://deepl.mpp.paywithlocus.com` | data | Professional translation and text improvement — translate text between 30+ langu... |
| **DeepSeek** | `https://deepseek.mpp.paywithlocus.com` | ai | Frontier AI models — DeepSeek-V3 for fast chat and code, DeepSeek-R1 for deep ch... |
| **Diffbot** | `https://diffbot.mpp.paywithlocus.com` | web, data | Web data extraction — articles, products, discussions, images, videos, and auto-... |
| **Diffbot KG** | `https://diffbot-kg.mpp.paywithlocus.com` | data | Knowledge Graph — search 10B+ entities and enrich company/person records. |
| **Diffbot NL** | `https://diffbot-nl.mpp.paywithlocus.com` | ai | Natural language processing — NER, sentiment, facts, summarization. |
| **EDGAR (SEC)** | `https://edgar.mpp.paywithlocus.com` | data | SEC EDGAR public financial data — company filing history, XBRL financial facts (... |
| **EDGAR Full-Text Search** | `https://edgar-search.mpp.paywithlocus.com` | data | Full-text search across all SEC filings — 10-Ks, 10-Qs, 8-Ks, proxy statements, ... |
| **Email Reputation** | `https://abstract-email-reputation.mpp.paywithlocus.com` | data | Check the reputation and risk score of an email address. |
| **Exa** | `https://exa.mpp.tempo.xyz` | search, ai | AI-powered web search, content retrieval, and answers. |
| **Exchange Rates** | `https://abstract-exchange-rates.mpp.paywithlocus.com` | data | Live, historical, and conversion exchange rates for 150+ currencies. |
| **fal.ai** | `https://fal.mpp.tempo.xyz` | ai, media | Image, video, and audio generation with 600+ models (Flux, SD, Recraft, Grok). |
| **Firecrawl** | `https://firecrawl.mpp.tempo.xyz` | web, data | Web scraping, crawling, and structured data extraction for LLMs. |
| **FlightAPI** | `https://flightapi.mpp.tempo.xyz` | data | Real-time flight prices, tracking, and airport schedules from 700+ airlines. |
| **GoFlightLabs** | `https://goflightlabs.mpp.tempo.xyz` | data | Real-time flight tracking, prices, schedules, and airline data. |
| **Google Maps** | `https://googlemaps.mpp.tempo.xyz` | data | Google Maps Platform — geocoding, directions, places, routes, tiles, weather, ai... |
| **Grok** | `https://grok.mpp.paywithlocus.com` | ai | xAI models — chat, web/X search, code execution, image generation/editing, and t... |
| **Groq** | `https://groq.mpp.paywithlocus.com` | ai | Ultra-fast LLM inference — Llama 3.3, DeepSeek R1, Gemma 2, GPT-OSS, Qwen, Whisp... |
| **Holidays** | `https://abstract-holidays.mpp.paywithlocus.com` | data | Public holiday data for 200+ countries. |
| **Hunter** | `https://hunter.mpp.paywithlocus.com` | data | Email finding, verification, and company enrichment for outreach and lead genera... |
| **IBAN Validation** | `https://abstract-iban-validation.mpp.paywithlocus.com` | data | Validate International Bank Account Numbers (IBANs). |
| **IP Intelligence** | `https://abstract-ip-intelligence.mpp.paywithlocus.com` | data | Detect VPNs, proxies, bots, and Tor nodes by IP address. |
| **IPinfo** | `https://ipinfo.mpp.paywithlocus.com` | data | IP intelligence — geolocation, ASN, privacy detection, carrier data, and hosting... |
| **Judge0** | `https://judge0.mpp.paywithlocus.com` | compute | Online code execution — run source code in 60+ programming languages with sandbo... |
| **KicksDB** | `https://kicksdb.mpp.tempo.xyz` | data | Sneaker & streetwear market data — prices, sales history, and availability from ... |
| **Mapbox** | `https://mapbox.mpp.paywithlocus.com` | data | Location and mapping APIs — geocoding, directions, isochrones, matrix routing, m... |
| **Mathpix** | `https://mathpix.mpp.paywithlocus.com` | ai | OCR for math, science, and documents — extract LaTeX, MathML, and Mathpix Markdo... |
| **Mistral AI** | `https://mistral.mpp.paywithlocus.com` | ai | Premier and open-source LLMs — Mistral Large, Medium, Small, Codestral, Magistra... |
| **Nansen** | `https://api.nansen.ai` | blockchain, data | Blockchain analytics and smart money intelligence. Token data, wallet profiling,... |
| **OpenWeather** | `https://openweather.mpp.paywithlocus.com` | data | Global weather data — current conditions, 5-day forecasts, hourly forecasts, air... |
| **Oxylabs** | `https://oxylabs.mpp.tempo.xyz` | web, data | Web scraping API with geo-targeting by country, state, and city. Fetch any publi... |
| **Parallel** | `https://parallelmpp.dev` | search, ai | Web search, page extraction, and multi-hop web research. |
| **Perplexity** | `https://perplexity.mpp.paywithlocus.com` | ai, search | AI-powered search — Sonar chat with real-time web grounding, web search, and emb... |
| **Phone Intelligence** | `https://abstract-phone-intelligence.mpp.paywithlocus.com` | data | Validate and get carrier info for phone numbers worldwide. |
| **PostalForm** | `https://postalform.com` | web | Print and mail real letters and documents via AI agents. |
| **Quicknode** | `https://mpp.quicknode.com` | blockchain | Quicknode Core Node API for 80+ blockchains and 140+ networks. |
| **RentCast** | `https://rentcast.mpp.paywithlocus.com` | data | US real estate intelligence — property records, AVM valuations, rent estimates, ... |
| **Replicate** | `https://replicate.mpp.paywithlocus.com` | ai, media | Run thousands of open-source AI models via API — image generation, language mode... |
| **ScreenshotOne** | `https://screenshotone.mpp.paywithlocus.com` | compute | Website screenshot API — capture any URL, HTML, or markdown as PNG, JPEG, WebP, ... |
| **SerpApi** | `https://serpapi.mpp.tempo.xyz` | search, data | Google Flights search — real-time prices, schedules, and booking options. |
| **SpyFu** | `https://spyfu.mpp.tempo.xyz` | data, search | Competitor keyword research — SEO rankings, PPC ads, ad history, and domain anal... |
| **Stability AI** | `https://stability-ai.mpp.paywithlocus.com` | ai, media | Generative AI platform for images, 3D models, and audio — text-to-image, editing... |
| **StableEmail** | `https://stableemail.dev` | social | Pay-per-send email delivery, forwarding inboxes, and custom subdomains — no API ... |
| **StableEnrich** | `https://stableenrich.dev` | data, search, social | Pay-per-request research APIs — people, companies, web search, scraping, places,... |
| **StablePhone** | `https://stablephone.dev` | ai, social | AI phone calls, dedicated phone numbers, and iMessage/FaceTime lookup — pay per ... |
| **StableSocial** | `https://stablesocial.dev` | social, data | Pay-per-request social media data from TikTok, Instagram, Facebook, and Reddit. |
| **StableStudio** | `https://stablestudio.dev` | ai, media | Pay-per-generation AI image and video creation — Nano Banana, GPT Image, Grok, F... |
| **StableTravel** | `https://stabletravel.dev` | data, web | Pay-per-request travel APIs — flights, hotels, activities, transfers, and real-t... |
| **StableUpload** | `https://stableupload.dev` | storage | Pay-per-upload file hosting and static site hosting with custom domains — 6 mont... |
| **Suno** | `https://suno.mpp.paywithlocus.com` | ai, media | AI music generation — create full songs, generate lyrics, and build custom music... |
| **Tavily** | `https://tavily.mpp.paywithlocus.com` | search, web | AI-optimized web search, content extraction, site mapping, and crawling API. |
| **Timezone** | `https://abstract-timezone.mpp.paywithlocus.com` | data | Current time and timezone conversion for any location. |
| **VAT** | `https://abstract-vat.mpp.paywithlocus.com` | data | VAT number validation, rate calculation, and category lookup for EU. |
| **Web Scraping** | `https://abstract-web-scraping.mpp.paywithlocus.com` | web, data | Scrape web pages with optional JavaScript rendering. |
| **Wolfram|Alpha** | `https://wolframalpha.mpp.paywithlocus.com` | data | Computational knowledge engine — math, science, geography, history, nutrition, f... |

## Stripe Services (3)

Fiat payment via **Stripe (USD)**. No crypto required.

| Service | URL | Description |
|---------|-----|-------------|
| **Prospect Butcher** | `https://agents.prospectbutcher.shop` | Order sandwiches for pickup in Brooklyn — the first food purchase made entirely  |
| **Stripe Climate** | `https://climate.stripe.dev` | Fund permanent carbon removal projects via Stripe Climate. |
| **Tako** | `https://tako.com` | Data visualization and research platform. Search datasets, generate charts, and  |
