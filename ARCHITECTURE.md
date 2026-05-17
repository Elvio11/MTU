# MTUS v1.0.0 - Architecture Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Directory Structure](#directory-structure)
3. [Agent Registry & File Mapping](#agent-registry--file-mapping)
4. [Database Schema](#database-schema)
5. [Configuration Files](#configuration-files)
6. [Environment Variables](#environment-variables)
7. [Paper Trading Implementation](#paper-trading-implementation)
8. [Ubuntu/WSL Setup](#ubuntuwsl-setup)

---

## System Overview

**MTUS (MemeTrader Unified System)** is an enterprise-grade multi-agent trading platform for Solana meme coin sniping.

### Core Technologies
- **Runtime**: Node.js 20 LTS (TypeScript agents) + Python 3.11+ (Python agents)
- **Message Bus**: Redis 7.x for inter-agent communication and instant Telegram notification routing
- **Database**: PostgreSQL (`mtus_db`) for high-concurrency position storage (SQLite remains as local sandbox fallback)
- **Blockchain**: Solana Mainnet via Helius/QuickNode/Alchemy RPC

### Agent Architecture (10 Agents)

| ID | Agent | Language | Purpose | Trigger |
|----|-------|----------|---------|---------|
| AGT-01 | NOFX | Python | Token Radar (PumpPortal WS) | Continuous stream |
| AGT-02 | Hermes | Python | Event Router | Event: token_qualified |
| AGT-03 | Anansi | Python | Safety Qualification (9 gates) | Event: token_received |
| AGT-04 | Oracle | Python | Price Polling (Birdeye/Jupiter) | 5s interval |
| AGT-05 | Ares | TypeScript | Trade Executor (Jupiter) | Event: trade_approved |
| AGT-06 | Sentinel | TypeScript | Position Monitor (TP/SL) | Continuous loop |
| AGT-07 | Janus | TypeScript | Capital Management | Scheduled + Event |
| AGT-08 | Cassandra | Python | Social Sentiment | Parallel to AGT-03 |
| AGT-09 | Ledger | Python | Audit Trail | Event: all trade events |
| AGT-10 | Heracles | Python | Guardian (Health/Kill Switch) | Continuous watchdog |

---

## Directory Structure

```
D:\Trader\                           # Project Root
├── ARCHITECTURE.md                   # This file
├── AGENT.md                         # Agent setup instructions
├── VERIFICATION_CHECKLIST.md        # Compliance checklist
├── converted.md                     # Technical specification (source of truth)
├── package.json                     # Node.js dependencies
├── tsconfig.json                    # TypeScript configuration
├── ecosystem.config.js             # PM2 process management
├── .env                            # Environment variables
│
├── config/
│   └── config.yaml                  # Master configuration (Section 6.1)
│
├── keystores/
│   ├── sniper.keystore              # Sniper wallet (encrypted, max 1.5 SOL)
│   └── main.keystore                # Main wallet (cold storage)
│
├── data/
│   └── positions.db                 # Sandbox SQLite database (fallback only)
│
├── redis/                           # Redis server (Windows)
│   ├── redis-server.exe
│   ├── redis-cli.exe
│   └── redis.windows.conf
│
├── src/
│   ├── python/                      # Python agents (L1, L2, L5)
│   │   ├── agents/
│   │   │   ├── nofx.py              # AGT-01: Token detection
│   │   │   ├── hermes.py            # AGT-02: Router
│   │   │   ├── anansi.py            # AGT-03: Safety gates (G1-G9)
│   │   │   ├── oracle.py            # AGT-04: Price polling
│   │   │   ├── cassandra.py         # AGT-08: Sentiment
│   │   │   ├── ledger.py            # AGT-09: Audit
│   │   │   ├── heracles.py          # AGT-10: Guardian
│   │   │   └── dashboard_bridge.py  # UI WebSocket bridge
│   │   │
│   │   └── shared/
│   │       ├── envelope.py          # AgentMessageEnvelope schema
│   │       ├── redis_client.py      # Redis connection (aioredis)
│   │       ├── telegram_bot.py      # Admin commands (/start, /status, /killswitch, etc.)
│   │       ├── telegram_auth.py     # HMAC OTP verification
│   │       ├── keystore.py          # Argon2id + XSalsa20-Poly1305 encryption
│   │       ├── paper_trading.py     # PaperTradingEngine
│   │       ├── notification_templates.py  # Telegram message templates
│   │       ├── rpc_health.py        # RPC load balancer + circuit breaker
│   │       ├── incident_response.py # P0/P1 incident handling
│   │       ├── rate_limiter.py      # 10 trades/hour, 3 concurrent positions
│   │       ├── position_validator.py  # 0.15 SOL cap enforcement
│   │       ├── rotating_logger.py   # Daily logs, 30-day retention
│   │       ├── logging_config.py    # Structured JSON logging
│   │       └── solana_simulator.py  # Jupiter swap simulation for honeypot detection
│   │
│   └── typescript/                 # TypeScript agents (L3, L4)
│       ├── agents/
│       │   ├── ares.ts              # AGT-05: Trade executor (Jupiter swaps)
│       │   ├── sentinel.ts          # AGT-06: Position monitor (TP/SL state machine)
│       │   ├── janus.ts             # AGT-07: Capital sweep
│       │   ├── ares_start.ts        # Agent entry point
│       │   ├── ares.test.ts         # Unit tests
│       │   ├── sentinel.test.ts     # Unit tests
│       │   └── janus.test.ts        # Unit tests
│       │
│       └── shared/
│           ├── envelope.ts          # TypeScript envelope schema
│           ├── db.ts                # PostgreSQL connection (node-postgres pool-backed)
│           ├── keystore.ts          # Keypair loading
│           ├── circuit-breaker.ts   # RPC circuit breaker
│           ├── operational-window.ts # 21:00-06:00 IST check
│           ├── mock_redis.ts        # In-memory Redis fallback (testing)
│           └── telegram_auth.ts     # OTP verification
│
├── dist/                           # Compiled TypeScript (build output)
│   ├── agents/
│   │   ├── ares.js
│   │   ├── sentinel.js
│   │   ├── janus.js
│   │   └── ares_start.js
│   └── shared/
│       ├── db.js
│       ├── envelope.js
│       ├── keystore.js
│       ├── mock_redis.js
│       └── ...
│
├── tests/                          # Python + TypeScript tests
│   ├── test_*.py                  # 66+ Python tests
│   └── *.test.ts                  # TypeScript tests
│
├── scripts/                       # Utility scripts
│   ├── generate_mock_wallets.py   # Create test keystores
│   ├── test_paper_trading.py      # Paper trading simulation
│   ├── start_agents.py           # Python agent launcher
│   ├── trigger_trade.js          # Test trade trigger
│   ├── paper_trade_direct.js      # Direct Jupiter quote test
│   └── combined_test.js           # Agent integration test
│
└── dashboard/                     # React UI (separate project)
    └── ...
```

---

## Agent Registry & File Mapping

### Python Agents (AGT-01, AGT-02, AGT-03, AGT-04, AGT-08, AGT-09, AGT-10)

| Agent | File | Purpose | Key Methods |
|-------|------|---------|-------------|
| **NOFX** | `src/python/agents/nofx.py` | PumpPortal WebSocket token detection | `connect()`, `subscribe()`, `reconnect_with_backoff()` |
| **Hermes** | `src/python/agents/hermes.py` | Route tokens to Anansi | `route_token()`, `check_operational_window()` |
| **Anansi** | `src/python/agents/anansi.py` | 9-gate qualification pipeline | `evaluate_token()`, `G1-G9 gates` |
| **Oracle** | `src/python/agents/oracle.py` | Birdeye/Jupiter/DexScreener price polling | `poll_prices()`, `fallback_chain()` |
| **Cassandra** | `src/python/agents/cassandra.py` | Social sentiment scoring | `fetch_sentiment()`, `calculate_score()` |
| **Ledger** | `src/python/agents/ledger.py` | Immutable trade records | `record_trade()`, `calculate_pnl()` |
| **Heracles** | `src/python/agents/heracles.py` | Guardian, health monitoring | `check_health()`, `kill_switch()`, `mainnet_readiness()` |

### TypeScript Agents (AGT-05, AGT-06, AGT-07)

| Agent | File | Purpose | Key Methods |
|-------|------|---------|-------------|
| **Ares** | `src/typescript/agents/ares.ts` | Jupiter swap execution | `executeTrade()`, `get_jupiter_quote()`, `broadcast_to_rpcs()` |
| **Sentinel** | `src/typescript/agents/sentinel.ts` | TP/SL state machine | `monitor_positions()`, `check_tp_sl()`, `sell_portion()` |
| **Janus** | `src/typescript/agents/janus.ts` | Capital sweep management | `check_balance()`, `top_up()`, `sweep()` |

### Shared Modules

| Module | File | Purpose |
|--------|------|---------|
| **Envelope** | `src/*/shared/envelope.ts|py` | AgentMessageEnvelope schema (JSON) |
| **Keystore** | `src/*/shared/keystore.ts|py` | Argon2id + XSalsa20-Poly1305 encryption |
| **Telegram** | `src/python/shared/telegram_bot.py` | Admin commands (10 commands implemented) |
| **Redis** | `src/python/shared/redis_client.py` | aioredis pub/sub |
| **DB** | `src/typescript/shared/db.ts` | PostgreSQL pool-backed storage (`pg`) |
| **Paper Trading** | `src/python/shared/paper_trading.py` | PaperTradingEngine class |
| **RPC Health** | `src/python/shared/rpc_health.py` | Load balancer + circuit breaker |
| **Notification** | `src/python/shared/notification_templates.py` | Telegram message templates |

---

## Database Schema

### PostgreSQL Tables (mtus_db)

```sql
-- Positions table (High-concurrency PostgreSQL backed)
CREATE TABLE positions (
    position_id         TEXT PRIMARY KEY,
    mint                TEXT NOT NULL,
    token_name          TEXT DEFAULT '',
    token_symbol        TEXT DEFAULT '',
    entry_price_sol     DOUBLE PRECISION DEFAULT 0,
    entry_amount_sol    DOUBLE PRECISION DEFAULT 0,
    tokens_received     DOUBLE PRECISION DEFAULT 0,
    entry_tx_signature  TEXT DEFAULT '',
    entry_timestamp_utc TEXT DEFAULT '',
    state               TEXT NOT NULL DEFAULT 'OPEN',
    tp1_price           DOUBLE PRECISION DEFAULT 0,
    tp2_price           DOUBLE PRECISION DEFAULT 0,
    sl_price            DOUBLE PRECISION DEFAULT 0,
    peak_price_sol      DOUBLE PRECISION DEFAULT 0,
    exit_price_sol      DOUBLE PRECISION,
    exit_tx_signature   TEXT,
    realised_pnl_sol    DOUBLE PRECISION,
    qualification_report TEXT,
    created_at          TEXT DEFAULT '',
    updated_at          TEXT DEFAULT ''
);

-- Index for fast open position queries (used on every monitoring tick)
CREATE INDEX idx_positions_state ON positions(state);

-- Audit Ledger (Append-only)
CREATE TABLE audit_ledger (
    id              SERIAL PRIMARY KEY,
    envelope_id     TEXT DEFAULT '',
    agent_id        TEXT DEFAULT '',
    event_type      TEXT DEFAULT '',
    payload         TEXT DEFAULT '',
    timestamp_utc   TEXT DEFAULT ''
);
```

### Redis Keys

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `mtus:agent:{agent_id}:health` | String | Agent health status (HEALTHY/UNHEALTHY) |
| `mtus:position:{position_id}` | Hash | Position data |
| `mtus:token:seen:{mint}` | String | Token dedup cache (TTL: 24h) |
| `mtus:config:*` | String | Runtime configuration |
| `mtus:circuit:{rpc_name}` | String | Circuit breaker state (CLOSED/OPEN/HALF_OPEN) |

---

## Configuration Files

### config/config.yaml (Section 6.1)

```yaml
system:
  trading_active: true
  operational_window:
    start_hour_ist: 21
    end_hour_ist: 6
  environment: paper  # production | paper

wallets:
  sniper_keystore_path: ./keystores/sniper.keystore
  main_keystore_path: ./keystores/main.keystore
  sniper_max_balance_sol: 1.5
  sniper_low_water_sol: 0.3

trading:
  position_size_sol: 0.15
  max_simultaneous_positions: 3
  max_trades_per_hour: 10
  daily_loss_limit_sol: 1.0

qualification:
  max_market_cap_sol: 150
  min_market_cap_sol: 5
  max_dev_holding_pct: 5
  max_top10_concentration_pct: 30
  min_lp_burned_pct: 85
  max_rugcheck_score: 300
```

---

## Environment Variables

### Required (.env)

```bash
# RPC Providers
HELIUS_KEY=your_helius_key
HELIUS_WSS=wss://mainnet.helius-rpc.com/?api-key=${HELIUS_KEY}
QUICKNODE_URL=https://...
ALCHEMY_URL=https://...

# Price APIs
BIRDEYE_API_KEY=your_birdeye_key
RUGCHECK_API_KEY=your_rugcheck_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_CHAT_ID=your_chat_id
TELEGRAM_OTP_SEED=your_otp_seed

# Redis (for WSL: redis://localhost:6379)
REDIS_URL=redis://localhost:6379

# Environment
MTUS_ENVIRONMENT=paper  # production | paper

# Wallets
SNIPER_KEYSTORE_PATH=./keystores/sniper.keystore
MAIN_KEYSTORE_PATH=./keystores/main.keystore
SNIPER_PASSPHRASE=test123
```

---

## Paper Trading Implementation

### Section 8.4 - Paper Trading Mode

The paper trading system intercepts Jupiter swap calls and simulates trades using real market prices.

### Flow:

1. **Quote Fetch** (FREE - Jupiter API)
   ```
   GET https://api.jup.ag/swap/v6/quote
   ?inputMint=So11111111111111111111111111111111111111112
   &outputMint={TOKEN_MINT}
   &amount={POSITION_SIZE_SOL * 1e9}
   &slippageBps=1000
   ```

2. **Price Extraction**
   - Entry price: `quote.outAmount / 1e9` (SOL per token)
   - Paper mode: Do NOT execute on-chain transaction

3. **Position Recording**
   - Write to `paper_positions` table
   - Mark with `[PAPER]` tag in Telegram notifications

4. **Exit Simulation**
   - Fetch exit quote from Jupiter when TP/SL triggers
   - Calculate PnL based on real prices

### Mainnet Readiness Gate (Section 8.4)

```
Required: 50+ trades, win rate > 40%, Sharpe ratio > 0.5
Command: /golive (requires OTP)
```

---

## Ubuntu/WSL Setup

### Requirements (Section 8.1, 8.2)

| Component | Version | Purpose |
|-----------|---------|---------|
| OS | Ubuntu 22.04 LTS | As per technical spec |
| Node.js | 20 LTS | TypeScript runtime |
| Python | 3.11+ | Python agents |
| Redis | 7.x | Message bus |

### Setup Commands

```bash
# 1. Install Node.js 20
curl -fsSL https://nodejs.org/dist/v20.18.0/node-v20.18.0-linux-x64.tar.xz -o /tmp/node.tar.xz
tar -xf /tmp/node.tar.xz -C /usr/local --strip-components=1

# 2. Install Python 3.11
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.11 python3.11-venv python3-pip

# 3. Install Redis
apt install -y redis-server

# 4. Configure Redis to bind all interfaces
sed -i 's/bind 127.0.0.1/bind 0.0.0.0/' /etc/redis/redis.conf
redis-server --daemonize yes

# 5. Access project (mounted at /mnt/d/Trader)
cd /mnt/d/Trader

# 6. Install dependencies
npm install
python3.11 -m pip install -r requirements.txt

# 7. Build TypeScript
npm run build

# 8. Test Redis
redis-cli ping  # Should return PONG

# 9. Start agents
node dist/agents/ares_start.js  # Start Ares
python -m src.python.agents.nofx  # Start NOFX
```

### Current WSL Status

- ✅ Node.js 20.18.0 installed
- ✅ Python 3.11.15 installed
- ✅ Redis running on port 6379
- ✅ npm dependencies installed
- ✅ TypeScript builds successfully

---

## Testing Status (Section 10)

| Test Type | Status | Coverage |
|-----------|--------|----------|
| Unit Tests (Python) | 66+ passing | ~90% |
| Unit Tests (TypeScript) | 31+ passing | ~85% |
| Integration | Partial | ~50% |
| E2E | Not implemented | - |
| Chaos | Not implemented | - |

---

## Key Implementation Notes

### Mock Redis (Development Only)
- Location: `src/typescript/shared/mock_redis.ts`
- Purpose: Fallback when Redis unavailable
- Not for production use

### Keystore Encryption
- Algorithm: Argon2id + XSalsa20-Poly1305
- KDF: time_cost=4, memory_cost=65536, parallelism=2
- Files: `keystores/sniper.keystore`, `keystores/main.keystore`

### Telegram Commands Implemented
- `/start`, `/help`, `/status`, `/pnl` (no auth)
- `/pause`, `/resume`, `/killswitch`, `/exit`, `/sweep`, `/config` (OTP required)

---

## Compliance Status (VERIFICATION_CHECKLIST.md)

- **Total Requirements**: ~120
- **Fully Implemented**: ~115 (95.8%)
- **Partially Implemented**: ~4 (3.3%)
- **NOT Implemented**: ~1 (0.8%)

### Remaining Gaps:
1. Full E2E test suite (requires live trading)
2. Chaos tests (RPC failure, Redis downtime simulation)
3. Security fuzzing tests

---

*Last Updated: 2026-05-05*
*Version: 1.0.0*
*Classification: CONFIDENTIAL*