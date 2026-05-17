# MTUS — MemeTrader Unified System

> Enterprise-grade multi-agent Solana meme coin trading platform with real-time detection, 11-gate safety qualification, Jupiter swap execution, and AI-powered control via MCP.

![Architecture](assets/architecture-hero.svg)

<div align="center">

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Python](https://img.shields.io/badge/python-3.11+-3b82f6.svg)
![TypeScript](https://img.shields.io/badge/typescript-5.2+-06b6d4.svg)
![Redis](https://img.shields.io/badge/redis-7.x-dc2626.svg)
![PostgreSQL](https://img.shields.io/badge/postgresql-14+-336791.svg)
![Tests](https://img.shields.io/badge/tests-327%20passing-10b981.svg)
![Agents](https://img.shields.io/badge/agents-13-8b5cf6.svg)

</div>

---

## Table of Contents

- [Features](#features)
- [System Architecture](#system-architecture)
- [Agent Registry](#agent-registry)
- [How It Works](#how-it-works)
- [Safety Pipeline](#safety-pipeline)
- [Position Management](#position-management)
- [Technology Stack](#technology-stack)
- [Quick Start](#quick-start)
- [Detailed Setup](#detailed-setup)
- [Configuration](#configuration)
- [Dashboard](#dashboard)
- [MCP Server](#mcp-server)
- [Security](#security)
- [Testing](#testing)
- [Process Management](#process-management)
- [Project Structure](#project-structure)
- [Scripts & Utilities](#scripts--utilities)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Features

- **13 Autonomous Agents** — Coordinated Python and TypeScript microservices communicating via Redis Pub/Sub
- **11-Gate Safety Pipeline** — Rigorous token qualification covering mint authority, LP burn, holder concentration, honeypot detection, and more
- **Jupiter Swap Execution** — Dual API strategy (V1 for small trades, V2 with RTSE for larger trades) for optimal slippage handling
- **TP/SL State Machine** — Sophisticated position management with take-profit, trailing stop, time-based exit, and dynamic resizing
- **Real-Time Dashboard** — Next.js 16 UI with WebSocket live updates, portfolio tracking, agent health monitoring, and trading controls
- **Telegram Admin Bot** — 10 commands with HMAC-OTP authentication for remote system control
- **Paper & Production Modes** — Full simulation mode for strategy validation before risking real capital
- **Dynamic Portfolio Sizing** — PnL-based compounding that adjusts position sizes based on performance
- **MCP Integration** — 13 AI tools via Model Context Protocol for natural-language system control
- **Enterprise Security** — Argon2id + XSalsa20-Poly1305 wallet encryption, circuit breakers, rate limiting, and kill switch

---

## System Architecture

![Architecture Overview](assets/architecture-hero.svg)

MTUS uses a **three-tier event-driven architecture**:

1. **Detection Layer** — Agents monitor PumpDev WebSocket, Pump.fun API, and DexScreener for new token events
2. **Execution Layer** — Qualified tokens flow through safety gates to Jupiter swap execution on Solana
3. **Monitoring Layer** — Open positions are tracked with real-time price polling and automated TP/SL management

All inter-agent communication flows through **Redis Pub/Sub** using the `mtus:channel:` namespace. Persistent state is stored in **PostgreSQL** (positions + audit ledger). Wallet keys are encrypted on disk with **Argon2id KDF + XSalsa20-Poly1305**.

---

## Agent Registry

| ID | Agent | Language | Purpose | Trigger |
|----|-------|----------|---------|---------|
| AGT-01 | NofxAgent | Python | Token radar via PumpDev/Whistle WebSocket | Continuous stream |
| AGT-02 | HermesAgent | Python | Event router — dispatches tokens to safety + sentiment | `token_detected` |
| AGT-03 | AnansiAgent | Python | 11-gate safety qualification pipeline | `token_received` |
| AGT-04 | Oracle | Python | Price polling (Jupiter V3, DexScreener, Birdeye) | 5s interval |
| AGT-05 | Ares | TypeScript | Jupiter swap trade executor with slippage ladder | `trade_approved` |
| AGT-06 | Sentinel | TypeScript | TP/SL state machine monitor | Continuous loop |
| AGT-07 | Janus | TypeScript | Capital sweep & wallet balance management | Scheduled + event |
| AGT-08 | CassandraAgent | Python | Social sentiment scoring | Parallel to AGT-03 |
| AGT-09 | LedgerAgent | Python | Append-only audit trail to PostgreSQL | All trade events |
| AGT-10 | HeraclesAgent | Python | Guardian — health monitoring, kill switch, readiness | Continuous watchdog |
| AGT-11 | DashboardBridge | Python | WebSocket server bridging Redis to Next.js UI | Continuous |
| AGT-12 | HydraAgent | Python | Trending token detection & bonding curve monitoring | 30s polling |
| AGT-13 | PortfolioSizer | Python | Dynamic position sizing via PnL compounding | `position_closed` |
| — | TelegramBot | Python | Admin commands (10 cmds, OTP-authenticated) | User input |
| — | MTUS-MCP | TypeScript | AI tool server (13 tools via Model Context Protocol) | AI agent calls |
| — | Dashboard | Next.js | Real-time UI (5 pages, REST + WebSocket) | Browser |

---

## How It Works

![Data Flow](assets/data-flow.svg)

### Trade Lifecycle

1. **Detection** — AGT-01 (NofxAgent) connects to PumpDev WebSocket and detects new token launches. Each token is assigned a priority score and enqueued in a Redis Sorted Set.

2. **Routing** — AGT-02 (HermesAgent) receives `token_detected` events and dispatches them in parallel to AGT-03 (safety) and AGT-08 (sentiment).

3. **Safety Qualification** — AGT-03 (AnansiAgent) runs the 11-gate pipeline. Tokens must pass all required gates (G1, G2, G7, G10, G11 in paper mode; all 11 in production) to receive approval.

4. **Execution** — AGT-05 (Ares) receives `trade_approved`, performs operational window and rate limit checks, fetches a Jupiter quote, signs the transaction, and broadcasts to Solana RPC.

5. **Monitoring** — AGT-06 (Sentinel) tracks the open position. AGT-04 (Oracle) polls prices every 5 seconds. The state machine evaluates TP/SL conditions on each tick.

6. **Closure** — When a trigger fires (TP1, TP2, SL, trailing, or time-based), Sentinel executes the exit. AGT-13 (PortfolioSizer) recalculates the next position size based on cumulative PnL.

7. **Audit** — AGT-09 (LedgerAgent) records every event to PostgreSQL for immutable audit trail.

---

## Safety Pipeline

![Safety Gates](assets/safety-gates.svg)

### Gate Definitions

| Gate | Check | Threshold | Source |
|------|-------|-----------|--------|
| G1 | Mint Authority Revoked | `mintAuthority == null` | RugCheck / RPC |
| G2 | Freeze Authority Revoked | `freezeAuthority == null` | RugCheck |
| G3 | LP Burned | ≥85% | RugCheck |
| G4 | Dev Holdings | <5% (disabled for pump.fun) | `getTokenLargestAccounts` |
| G5 | Top 10 Concentration | <30% | `getTokenLargestAccounts` |
| G6 | RugCheck Score | ≤999 | RugCheck API |
| G7 | Market Cap Range | 5–150 SOL | Token payload |
| G8 | Social Metadata | ≥1 social link | Token URI fetch |
| G9 | Duplicate Check | Not seen in 24h | Redis `mtus:dedup:{mint}` |
| G10 | Honeypot Check | No freeze/mint authority | `getAccountInfo` |
| G11 | Bonding Curve Health | ≥30 SOL in curve | Token payload |

### Enforcement Modes

- **Paper Mode**: G1, G2, G7, G10, G11 enforced (G3–G9 skipped)
- **Production Mode**: All 11 gates enforced

---

## Position Management

### State Machine

![Sentinel States](assets/sentinel-states.svg)

Positions transition through a deterministic state machine:

| State | Trigger | Action |
|-------|---------|--------|
| `OPEN` | Entry confirmed | Monitor for TP1 or SL |
| `TAKE_PROFIT_1` | Price ≥ entry × 2.0 | Sell 50%, start trailing at 85% of peak |
| `TRAILING` | Price ≤ peak × 0.85 | Sell remaining 50% |
| `TAKE_PROFIT_2` | Price ≥ entry × 5.0 | Sell remaining 50% |
| `STOP_LOSS` | Price ≤ entry × 0.7 | Sell 100% |
| `TIME_SL` | 4 hours without TP1 | Force sell 100% |
| `CLOSED` | All tokens sold | Position complete |
| `FAILED` | Trade execution error | Logged, no position opened |

### Price Ladder

![TP/SL Ladder](assets/tp-sl-ladder.svg)

---

## Technology Stack

![Tech Stack](assets/tech-stack.svg)

### Runtime & Languages

| Component | Technology | Version |
|-----------|------------|---------|
| Python Agents | Python + asyncio | 3.11+ |
| TypeScript Agents | Node.js + TypeScript | 20 LTS / 5.2+ |
| Dashboard | Next.js + React | 16.2.4 / 19.2.4 |
| MCP Server | TypeScript + MCP SDK | 1.29.0 |

### Infrastructure

| Component | Technology | Purpose |
|-----------|------------|---------|
| Message Bus | Redis 7.x | Pub/Sub inter-agent communication |
| Database | PostgreSQL 14+ | Positions table + audit ledger |
| Process Mgmt (TS) | PM2 | Ares, Sentinel, Janus |
| Process Mgmt (Python) | Supervisor | All Python agents |
| Encryption | Argon2id + XSalsa20-Poly1305 | Wallet keystore protection |

### Blockchain

| Component | Technology | Purpose |
|-----------|------------|---------|
| Blockchain | Solana Mainnet | Token execution |
| DEX Aggregator | Jupiter API V1/V2/V3 | Swap quotes + price data |
| Token Platform | Pump.fun | New token launches |
| RPC Providers | Helius, QuickNode, Alchemy | Transaction broadcast |
| Price Oracles | Jupiter V3, DexScreener, Birdeye | Real-time pricing |

### Key Dependencies

**Python**: `websockets`, `aioredis`, `pydantic`, `solana`, `solders`, `psycopg2-binary`, `argon2-cffi`, `pynacl`, `numpy`

**TypeScript**: `@solana/web3.js`, `@solana/spl-token`, `@jup-ag/api`, `ioredis`, `pg`, `argon2`, `tweetnacl`

**Dashboard**: `next`, `react`, `tailwindcss`, `recharts`, `lucide-react`, `vitest`, `@playwright/test`

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Elvio11/MTU.git
cd MTU

# 2. Install dependencies
npm install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your RPC keys, Telegram credentials, and wallet config

# 4. Start (paper mode by default)
npm run build
npm run start:all
```

---

## Detailed Setup

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Node.js | 20 LTS | TypeScript runtime |
| Python | 3.11+ | Python agents |
| Redis | 7.x | Message bus (must be running) |
| PostgreSQL | 14+ | Position storage (recommended) |

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# === REQUIRED: RPC Providers ===
HELIUS_KEY=your_helius_api_key
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=${HELIUS_KEY}
HELIUS_WSS=wss://mainnet.helius-rpc.com/?api-key=${HELIUS_KEY}
QUICKNODE_URL=https://your-quicknode-url
ALCHEMY_RPC_URL=https://solana-mainnet.g.alchemy.com/v2/your_key

# === REQUIRED: Redis ===
REDIS_URL=redis://localhost:6379

# === REQUIRED: PostgreSQL ===
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/mtus_db

# === REQUIRED: Environment Mode ===
MTUS_ENVIRONMENT=paper          # "paper" for testing, "production" for live

# === REQUIRED: Wallet Configuration ===
SNIPER_KEYSTORE_PATH=./keystores/sniper.keystore
MAIN_KEYSTORE_PATH=./keystores/main.keystore
SNIPER_PASSPHRASE=your_passphrase

# === OPTIONAL: Price APIs ===
BIRDEYE_API_KEY=your_birdeye_key
RUGCHECK_API_KEY=your_rugcheck_key

# === OPTIONAL: Telegram Bot ===
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_CHAT_ID=your_chat_id
TELEGRAM_OTP_SEED=your_otp_seed
```

### Redis Setup

```bash
# Linux
sudo apt install redis-server
redis-server --daemonize yes
redis-cli ping  # Should return PONG

# Windows (included in repo)
./redis/redis-server.exe
```

### PostgreSQL Setup

```bash
# Create database
createdb mtus_db

# Initialize schema
python scripts/init_db.py
```

### Wallet Setup

Keystores are encrypted wallet files. Generate them with:

```bash
# Generate test keystores
python scripts/generate_keystores.py
# or
npx ts-node scripts/generate_keystores.ts
```

### Paper vs Production Mode

| Setting | Paper Mode | Production Mode |
|---------|-----------|----------------|
| `MTUS_ENVIRONMENT` | `paper` | `production` |
| Trade Execution | Simulated (no on-chain tx) | Real Jupiter swaps |
| Safety Gates | G1, G2, G7, G10, G11 | All 11 gates |
| Fund Risk | None | Real SOL at risk |

**Always test extensively in paper mode before switching to production.**

---

## Configuration

### Master Configuration (`config/config.yaml`)

The master config controls trading parameters, wallet thresholds, RPC weights, and qualification thresholds. Key sections:

```yaml
system:
  trading_active: true
  operational_window:
    start_hour_ist: 0
    end_hour_ist: 24
  environment: paper

trading:
  position_size_sol: 0.0005
  max_simultaneous_positions: 1
  max_trades_per_hour: 3
  daily_loss_limit_sol: 0.002
  tp1_multiplier: 2.0
  tp2_multiplier: 5.0
  sl_multiplier: 0.7
  trailing_stop_pct: 15
  time_sl_hours: 4
  priority_fee_cap_sol: 0.001

qualification:
  max_market_cap_sol: 150
  min_market_cap_sol: 5
  min_lp_burned_pct: 85
  max_rugcheck_score: 999
  min_virtual_sol_reserves: 30
```

### Redis Runtime Keys

Configuration can be updated at runtime via Redis keys or the Dashboard Settings page:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `mtus:trading_mode` | String | `"paper"` | Trading mode |
| `mtus:position_size_sol` | Number | `0.0005` | Position size in SOL |
| `mtus:max_positions` | Number | `1` | Max concurrent positions |
| `mtus:tp1_multiplier` | Number | `2.0` | Take profit 1 multiplier |
| `mtus:tp2_multiplier` | Number | `5.0` | Take profit 2 multiplier |
| `mtus:sl_multiplier` | Number | `0.7` | Stop loss multiplier |
| `mtus:trading_active` | Boolean | `true` | Trading active state |
| `mtus:killswitch_triggered` | Boolean | `false` | Kill switch state |
| `mtus:priority_fee_cap_sol` | Number | `0.001` | Priority fee cap |

---

## Dashboard

The MTUS Dashboard is a **Next.js 16** application with real-time WebSocket updates.

### Pages

| Page | Path | Description |
|------|------|-------------|
| Home | `/` | Portfolio summary, live prices, agent status, P&L chart |
| Agents | `/agents` | Agent health monitoring with heartbeat tracking |
| Positions | `/positions` | Open/closed positions with manual close |
| History | `/history` | Trade history with filters and CSV export |
| Settings | `/settings` | Trading config, wallet balances, admin controls |

### Real-Time Features

- **WebSocket** connection to `ws://localhost:3001` (DashboardBridge)
- **REST API fallback** via Next.js API routes (`/api/positions`, `/api/config`, `/api/wallets`, `/api/control`)
- **Live price updates** from Oracle agent
- **Agent health** with heartbeat timestamps
- **Trading controls** — pause, resume, kill switch (OTP required)

### Running the Dashboard

```bash
cd dashboard
npm install
npm run dev        # Development on port 5454
npm run build      # Production build
npm start          # Production server
```

---

## MCP Server

The **MTUS-MCP** server provides 13 AI tools via the [Model Context Protocol](https://modelcontextprotocol.io/), enabling AI agents (Claude, GPT, etc.) to control and monitor the trading system through natural language.

![MCP Architecture](assets/mcp-architecture.svg)

### Available Tools

| Tool | Description |
|------|-------------|
| `get_config` | Retrieve current trading configuration |
| `update_config` | Update a configuration value |
| `get_positions` | List open and closed positions |
| `get_balance` | Check wallet SOL balance |
| `get_pnl` | Get profit/loss statistics |
| `get_agents` | List all agents and their health status |
| `pause_trading` | Pause all trading activity |
| `resume_trading` | Resume trading after pause |
| `kill_switch` | Emergency stop all trading |
| `get_alerts` | Retrieve system alerts |
| `get_sniper_address` | Get sniper wallet address (secure) |
| `get_audit_log` | Query the audit ledger |
| `decrypt_keystore` | Decrypt wallet keystore (Argon2id) |

### Setup

```bash
cd mtus-mcp
npm install
npm run build
```

Configure your AI client (e.g., Claude Desktop) with the MCP server pointing to `mtus-mcp/dist/index.js`.

---

## Security

### Wallet Encryption

Wallet keys are encrypted using **Argon2id KDF + XSalsa20-Poly1305**:

- **KDF**: `time_cost=4`, `memory_cost=65536`, `parallelism=2`, `hash_len=32`
- **Cipher**: XSalsa20-Poly1305 (via `pynacl` / `tweetnacl`)
- **Storage**: `.keystore` JSON files with hex-encoded salt, nonce, and ciphertext

### Security Layers

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| Encryption | Argon2id + XSalsa20-Poly1305 | Wallet key protection |
| Authentication | HMAC-SHA256 OTP | Telegram admin commands |
| Rate Limiting | Redis-based counters | Max trades/hour, max concurrent positions |
| Circuit Breaker | Failure tracking per RPC | Auto-disable failing RPCs after 3 failures |
| Kill Switch | Redis flag + OTP | Emergency stop all trading |
| Audit Trail | PostgreSQL append-only | Immutable event logging |
| Operational Window | Time-based check | Trading only during configured hours |
| Daily Loss Limit | Redis counter | Auto-stop after daily loss threshold |

### Security Checklist

- [x] Wallet keys encrypted (never plaintext)
- [x] `.env` file excluded from git (`.gitignore`)
- [x] Keystore files excluded from git
- [x] Rate limiting enforced (Redis)
- [x] Kill switch available (Telegram + Dashboard)
- [x] Audit trail in PostgreSQL
- [x] Paper trading mode for testing
- [x] OTP required for destructive commands

---

## Testing

### Test Suite Summary

| Category | Location | Framework | Tests |
|----------|----------|-----------|-------|
| Unit Tests (Python) | `tests/unit/` | pytest | 83 |
| Integration Tests | `tests/integration/` | pytest + real Redis | 74 |
| E2E Tests | `tests/e2e/` | pytest | 83 |
| Chaos Tests | `tests/chaos/` | pytest | 6 |
| Security Tests | `tests/security/` | pytest | 15 |
| TypeScript Tests | `src/typescript/` | Jest | 41 |
| Dashboard Tests | `dashboard/` | Vitest | 25 |
| **Total** | | | **327** |

### Running Tests

```bash
# All Python tests
python -m pytest tests/ -v

# All TypeScript tests
npm test

# TypeScript with coverage
npm run test:coverage

# Dashboard tests
cd dashboard && npm run test:run

# Specific test file
python -m pytest tests/unit/test_priority_queue.py -v
```

---

## Process Management

### PM2 (TypeScript Agents + Dashboard)

```bash
# Start all processes
npm run start:all

# Start individual agents
npm run start:ares
npm run start:sentinel
npm run start:janus

# Monitor
pm2 status
pm2 logs

# Production config
pm2 start production.config.js
```

### Supervisor (Python Agents)

```bash
# Start all Python agents
supervisord -c supervisor.conf

# Control
supervisorctl -c supervisor.conf status
supervisorctl -c supervisor.conf restart mtus_python:
```

---

## Project Structure

```
MTU/
├── assets/                          # SVG diagrams for documentation
│   ├── architecture-hero.svg        # Full system topology
│   ├── data-flow.svg                # Token lifecycle flow
│   ├── sentinel-states.svg          # TP/SL state machine
│   ├── safety-gates.svg             # 11-gate qualification pipeline
│   ├── tech-stack.svg               # Technology stack visualization
│   ├── priority-queue.svg           # Priority queue scoring
│   ├── tp-sl-ladder.svg             # TP/SL price levels
│   └── mcp-architecture.svg         # MCP server architecture
│
├── src/
│   ├── python/                      # Python agents (7 agents + shared)
│   │   ├── agents/
│   │   │   ├── anansi.py            # AGT-03: Safety gates (G1-G11)
│   │   │   ├── cassandra.py         # AGT-08: Social sentiment
│   │   │   ├── dashboard_bridge.py  # AGT-11: WebSocket server
│   │   │   ├── heracles.py          # AGT-10: Guardian/kill switch
│   │   │   ├── hermes.py            # AGT-02: Event router
│   │   │   ├── hydra.py             # AGT-12: Trending tokens
│   │   │   ├── ledger.py            # AGT-09: Audit trail
│   │   │   ├── nofx.py              # AGT-01: Token radar
│   │   │   ├── oracle.py            # AGT-04: Price polling
│   │   │   ├── portfolio_sizer.py   # AGT-13: Dynamic sizing
│   │   │   └── telegram_bot_agent.py# Telegram admin bot
│   │   └── shared/                  # 28 shared Python modules
│   │       ├── api_manager.py       # API rate limiting + circuit breaker
│   │       ├── bonding_curve.py     # Pump.fun curve decoder
│   │       ├── circuit_breaker.py   # RPC failure tracking
│   │       ├── config_validator.py  # YAML config validation
│   │       ├── constants.py         # Redis keys, channels, agent IDs
│   │       ├── db.py                # PostgreSQL connection (psycopg2)
│   │       ├── envelope.py          # AgentMessageEnvelope schema
│   │       ├── indicators.py        # RSI, volume trend analysis
│   │       ├── keystore.py          # Argon2id + XSalsa20 encryption
│   │       ├── operational_window.py# Time-based trading check
│   │       ├── paper_trading.py     # Paper trading engine
│   │       ├── priority_queue.py    # Redis Sorted Set queue
│   │       ├── rate_limiter.py      # Trade rate limiting
│   │       ├── validators.py        # Input validation
│   │       └── ...                  # (+ 14 more modules)
│   │
│   └── typescript/                  # TypeScript agents (3 agents + shared)
│       ├── agents/
│       │   ├── ares.ts              # AGT-05: Trade executor
│       │   ├── ares_start.ts        # Ares entry point
│       │   ├── janus.ts             # AGT-07: Capital sweep
│       │   ├── janus_start.ts       # Janus entry point
│       │   ├── sentinel.ts          # AGT-06: TP/SL monitor
│       │   └── sentinel_start.ts    # Sentinel entry point
│       └── shared/                  # 27 shared TypeScript modules
│           ├── channels.ts          # Channel constants
│           ├── circuit-breaker.ts   # RPC circuit breaker
│           ├── config_validator.ts  # Config validation
│           ├── db.ts                # PostgreSQL (node-postgres pool)
│           ├── envelope.ts          # AgentMessageEnvelope schema
│           ├── keystore.ts          # Keypair loading
│           ├── mock_redis.ts        # Test Redis fallback
│           ├── operational-window.ts# Time check
│           ├── redis.ts             # Robust Redis client
│           ├── telegram_auth.ts     # OTP verification
│           └── check_balance.ts     # SOL balance checking
│
├── dashboard/                       # Next.js 16 UI
│   ├── src/
│   │   ├── app/                    # App router (5 pages + API routes)
│   │   ├── components/             # React components
│   │   ├── lib/                    # WebSocket client, API helpers
│   │   └── test/                   # Vitest tests
│   └── package.json
│
├── mtus-mcp/                        # Model Context Protocol server
│   ├── src/
│   │   └── index.ts                # 13 MCP tools
│   └── package.json
│
├── config/
│   └── config.yaml                 # Master configuration
│
├── scripts/                         # Utility scripts
│   ├── generate_keystores.py       # Create test keystores
│   ├── init_db.py                  # Initialize PostgreSQL schema
│   ├── transfer_sol.py             # SOL transfer utility
│   ├── manual_trade.js             # Manual trade trigger
│   └── verify_system.js            # System health check
│
├── tests/                           # Test suites
│   ├── unit/                       # Unit tests (Python)
│   ├── integration/                # Integration tests (real Redis)
│   ├── e2e/                        # End-to-end tests
│   ├── chaos/                      # Chaos tests (RPC/Redis failure)
│   └── security/                   # Security tests
│
├── .env.example                     # Environment variable template
├── .gitignore                       # Git ignore rules
├── package.json                     # Node.js dependencies
├── requirements.txt                 # Python dependencies
├── tsconfig.json                    # TypeScript configuration
├── ecosystem.config.js              # PM2 development config
├── production.config.js             # PM2 production config
├── supervisor.conf                  # Supervisor config for Python agents
├── jest.config.js                   # Jest configuration
└── pytest.ini                       # Pytest configuration
```

---

## Scripts & Utilities

| Script | Language | Purpose |
|--------|----------|---------|
| `scripts/generate_keystores.py` | Python | Generate encrypted test keystores |
| `scripts/generate_keystores.ts` | TypeScript | Generate encrypted test keystores (TS) |
| `scripts/init_db.py` | Python | Initialize PostgreSQL schema |
| `scripts/transfer_sol.py` | Python | Transfer SOL between wallets |
| `scripts/manual_trade.js` | JavaScript | Trigger manual trade for testing |
| `scripts/verify_system.js` | JavaScript | System health verification |
| `scripts/test_live_trade_flow.js` | JavaScript | Live trade flow test |

---

## Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) for details on our code of conduct, development setup, and PR process.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Jupiter Aggregator](https://jup.ag/) — DEX aggregation for optimal swap routing
- [Solana](https://solana.com/) — High-performance blockchain
- [Pump.fun](https://pump.fun/) — Token launch platform
- [DexScreener](https://dexscreener.com/) — Real-time token data
- [Helius](https://helius.dev/) — Solana RPC provider
- [Redis](https://redis.io/) — In-memory data store for message bus
- [Model Context Protocol](https://modelcontextprotocol.io/) — AI tool integration

---

<div align="center">

**MTUS v1.0.0** — Built with Python, TypeScript, and Solana

</div>
