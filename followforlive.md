# 🚀 Live Trading Preparation Plan

> **Reference**: TECHNICAL_DOCUMENTATION.md (MTUS System)
> **Environment**: `MTUS_ENVIRONMENT=production`

---

## Phase 1: Pre-Flight Verification

### 1.1 Code & Build Verification
```bash
# Run ALL Python tests (Reference: Section 10.2)
cd D:/Trader
python -m pytest tests/unit/ tests/integration/ tests/chaos/ tests/security/ -v --tb=short

# Verify TypeScript build (Reference: Section 9.6)
npm run build

# Expected: 98+ Python tests pass, TypeScript build succeeds
```

### 1.2 Redis Connectivity Check
```bash
# Start Redis (Reference: Appendix A.1)
cd D:/Trader/redis
redis-server.exe

# Verify connection
redis-cli ping
# Expected: PONG
```

### 1.3 Wallet Balance Verification
```bash
# Check sniper wallet balance (Reference: Section 3.5, 5.1)
# Required: Position size (0.0005 SOL) + fees (0.002 SOL buffer) = ~0.003 SOL minimum
# Wallet: ESHH2KcsMWSKoA6ypBGfbpP8Mre3k1QVw4jkypn8A1xc

# Check main wallet balance for sweep operations (Reference: Section 3.7, AGT-07)
# Wallet: FFtyqaLq9ApacZDBa1T4uXbyQnyexXhRXjg8XiSoPc1a

# Verify via dashboard: http://localhost:3000/wallets
```

---

## Phase 2: Environment Configuration for Production

### 2.1 Update `.env` File (Reference: Section 5.1)
```bash
# CRITICAL: Change environment mode
MTUS_ENVIRONMENT=production  # Was: "paper"

# Verify ALL required variables are set:
HELIUS_KEY=your_actual_helius_key
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=${HELIUS_KEY}
HELIUS_WSS=wss://mainnet.helius-rpc.com/?api-key=${HELIUS_KEY}

QUICKNODE_URL=https://your-quicknode-url
ALCHEMY_RPC_URL=https://solana-mainnet.g.alchemy.com/v2/your_key

REDIS_URL=redis://localhost:6379

# Telegram Bot (REQUIRED for admin)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_CHAT_ID=your_chat_id
TELEGRAM_OTP_SEED=your_otp_seed

# Wallet Configuration (REQUIRED)
SNIPER_KEYSTORE_PATH=./keystores/sniper.keystore
MAIN_KEYSTORE_PATH=./keystores/main.keystore
SNIPER_PASSPHRASE=your_passphrase

# Price APIs (OPTIONAL but recommended)
BIRDEYE_API_KEY=your_birdeye_key
RUGCHECK_API_KEY=your_rugcheck_key
```

### 2.2 Verify Keystore Files Exist (Reference: Section 8.1)
```bash
ls -la D:/Trader/keystores/
# Expected: sniper.keystore, main.keystore
```

### 2.3 Dashboard Environment (Reference: Section 9.6)
```bash
# Create D:/Trader/dashboard/.env.local
NEXT_PUBLIC_WS_URL=ws://localhost:3001
POSITIONS_DB_PATH=D:/Trader/data/positions.db
NEXT_PUBLIC_BIRDEYE_API_KEY=your_key  # Optional
```

---

## Phase 3: Agent Startup Sequence

### 3.1 Start Order (Reference: Appendix A)

**Terminal 1: Redis**
```bash
cd D:/Trader/redis
redis-server.exe
```

**Terminal 2: NOFX (AGT-01) - Token Detection**
```bash
cd D:/Trader
python -m src.python.agents.nofx
# Expected: "AGT-01: Connected to Redis and Priority Queue"
# Expected: "AGT-01: Connected to PumpDev WebSocket"
```

**Terminal 3: Hermes (AGT-02) - Event Router**
```bash
cd D:/Trader
python -m src.python.agents.hermes
# Expected: "AGT-02: Starting queue processor..."
```

**Terminal 4: Anansi (AGT-03) - Safety Gates**
```bash
cd D:/Trader
python -m src.python.agents.anansi
# Expected: Subscribes to mtus:channel:token_received
```

**Terminal 5: Oracle (AGT-04) - Price Polling**
```bash
cd D:/Trader
python -m src.python.agents.oracle
# Expected: Polls prices every 5s
```

**Terminal 6: Cassandra (AGT-08) - Social Sentiment**
```bash
cd D:/Trader
python -m src.python.agents.cassandra
# Expected: "AGT-08: Subscribed to token_received_social"
```

**Terminal 7: Ledger (AGT-09) - Audit Trail**
```bash
cd D:/Trader
python -m src.python.agents.ledger
# Expected: "AGT-09: Subscribed to event channels"
```

**Terminal 8: Heracles (AGT-10) - Guardian**
```bash
cd D:/Trader
python -m src.python.agents.heracles
# Expected: Health monitoring active
```

**Terminal 9: Ares (AGT-05) - Trade Execution (TypeScript)**
```bash
cd D:/Trader
node dist/agents/ares_start.js
# Expected: "AGT-05: [STARTED] Ares Agent running..."
# Expected: "AGT-05: Subscribed to trade_approved channel"
```

**Terminal 10: Sentinel (AGT-06) - TP/SL Monitor (TypeScript)**
```bash
cd D:/Trader
node dist/agents/sentinel_start.js
# Expected: Monitors open positions
```

**Terminal 11: Janus (AGT-07) - Balance Sweep (TypeScript)**
```bash
cd D:/Trader
node dist/agents/janus_start.js
# Expected: "AGT-07: Loaded wallets"
```

**Terminal 12: Dashboard Bridge (AGT-11)**
```bash
cd D:/Trader
python -m src.python.agents.dashboard_bridge
# Expected: WebSocket server on ws://0.0.0.0:3001
```

**Terminal 13: Dashboard (Next.js)**
```bash
cd D:/Trader/dashboard
npm run dev
# Opens at http://localhost:3000
```

---

## Phase 4: Health Verification

### 4.1 Agent Health Check (Reference: Section 9.5)
```bash
# Check dashboard at http://localhost:3000/agents
# Verify ALL 11 agents show "healthy" status:
# AGT-01 (NOFX), AGT-02 (Hermes), AGT-03 (Anansi)
# AGT-04 (Oracle), AGT-05 (Ares), AGT-06 (Sentinel)
# AGT-07 (Janus), AGT-08 (Cassandra), AGT-09 (Ledger)
# AGT-10 (Heracles), AGT-11 (DashboardBridge)
```

### 4.2 Message Flow Verification (Reference: Section 7)
```bash
# Test complete flow: NOFX → Hermes → Anansi → Ares
# 1. NOFX detects token → enqueues to mtus:trade_queue
# 2. Hermes dequeues → publishes to mtus:channel:token_received
# 3. Anansi receives → runs G1-G11 → publishes mtus:channel:trade_approved
# 4. Ares receives → executes trade → publishes mtus:channel:position_opened
# 5. Sentinel receives → starts monitoring

# Watch Redis pub/sub:
redis-cli
SUBSCRIBE mtus:channel:token_detected mtus:channel:trade_approved mtus:channel:position_opened
```

### 4.3 Priority Queue Verification (Reference: Section 3.1, priority_queue.py)
```bash
# Check queue is empty before trading
redis-cli
ZCARD mtus:trade_queue
# Expected: 0

# Verify priority ordering (lower score = higher priority)
# Priority 1 (migration) should dequeue first
# Priority 3 (new tokens) should dequeue last
```

---

## Phase 5: Live Trading Test Scenarios

### 5.1 Initial Test with Minimum Position Size (Reference: Section 3.5)
```bash
# Verify position size is set to minimum:
redis-cli GET mtus:position_size_sol
# Expected: 0.0005 (or lower for first test)

# Alternative: Edit D:/Trader/config/config.yaml:
# trading:
#   position_size_sol: 0.0005  # Minimum for first test
```

### 5.2 Full Trade Cycle Test (Reference: Section 7.2)
```
1. Wait for NOFX to detect a new token (PumpDev WebSocket)
2. Verify token enters mtus:trade_queue (priority based on type)
3. Watch Hermes dequeue and route to Anansi
4. Verify Anansi runs G1-G11 safety gates:
   - G1: Mint Authority Revoked (null)
   - G2: Freeze Authority Revoked (null)
   - G3: LP Burned ≥85%
   - G4: Dev Holdings <5% (disabled for pump.fun)
   - G5: Top 10 Concentration <30%
   - G6: RugCheck Score ≤999
   - G7: Market Cap 5-150 SOL
   - G8: Social Metadata ≥1 link
   - G9: Not duplicate (24h)
   - G10: Honeypot Check (no freeze/mint)
   - G11: Bonding Curve Health ≥30 SOL
5. If approved: Ares executes trade via Jupiter
6. Sentinel starts monitoring for TP/SL
7. Position appears in dashboard
```

### 5.3 TP/SL Trigger Test (Reference: Section 3.6, 7.3)
```
1. After position opens, monitor price updates:
   - Oracle polls every 5s → publishes mtus:channel:price_updated
   - Sentinel receives → updates position state

2. Verify TP1 trigger (price ≥ 2x entry):
   - Sentinel sells 50%
   - Publishes mtus:channel:tp1_hit
   - Trailing stop at 85% of peak

3. Verify SL trigger (price ≤ 0.7x entry):
   - Sentinel sells 100%
   - Publishes mtus:channel:stop_loss_hit

4. Verify TP2 trigger (price ≥ 5x entry):
   - Sentinel sells remaining 50%
   - Publishes mtus:channel:tp2_hit

5. Verify Time SL (4h without TP1):
   - Sentinel force-sells all
   - Publishes mtus:channel:time_sl_hit
```

### 5.4 Dashboard Monitoring Test (Reference: Section 9)
```
1. Open http://localhost:3000
2. Verify Dashboard Home shows:
   - Portfolio summary
   - Live token prices
   - Agent status (all healthy)
   - System alerts
   - Open positions
   - P&L chart

3. Check Positions page (/positions):
   - See open/closed positions
   - Manual close button works (requires OTP)

4. Check History page (/history):
   - Trade history with filters
   - CSV export works

5. Check Settings page (/settings):
   - Trading mode toggle (Paper/Live)
   - Position size adjustment
   - TP/SL multiplier changes
   - Pause/Resume/Kill Switch buttons (require OTP)
```

---

## Phase 6: Emergency Procedures

### 6.1 Kill Switch Activation (Reference: Section 8.1, Appendix B)
```bash
# Method 1: Telegram Bot (Reference: Appendix B)
# Send: /killswitch <otp>
# Expected: All trading stops, positions closed

# Method 2: Dashboard (Reference: Section 9.5)
# Settings page → Kill Switch button → Enter OTP

# Method 3: Redis direct
redis-cli SET mtus:killswitch_triggered true
# Heracles (AGT-10) detects and triggers shutdown

# Verify:
redis-cli GET mtus:killswitch_triggered
# Expected: "true"
```

### 6.2 Pause/Resume Trading (Reference: Section 8.1)
```bash
# Pause via Telegram:
# Send: /pause <otp>

# Resume via Telegram:
# Send: /resume <otp>

# Check status:
redis-cli GET mtus:trading_paused
# Expected: "true" when paused, "false" when active
```

### 6.3 Manual Position Close (Reference: Appendix B)
```bash
# Telegram:
# Send: /exit <position_id> <otp>

# Dashboard:
# Positions page → Click "Close" → Enter OTP

# Verify:
# - Sentinel stops monitoring
# - Ares executes sell order
# - Position state → CLOSED
# - Audit ledger updated
```

---

## Phase 7: Post-Trade Verification

### 7.1 Audit Ledger Check (Reference: Section 6.1, audit_ledger table)
```sql
-- Check D:/Trader/data/positions.db
SELECT * FROM audit_ledger ORDER BY id DESC LIMIT 20;

-- Verify events logged:
-- token_detected, token_received, trade_approved, position_opened,
-- tp1_hit, stop_loss_hit, position_closed
```

### 7.2 Position Verification (Reference: Section 6.1, positions table)
```sql
-- Check open positions
SELECT position_id, mint, entry_price_sol, state FROM positions WHERE state != 'CLOSED';

-- Check closed positions with P&L
SELECT position_id, mint, realised_pnl_sol FROM positions WHERE state = 'CLOSED';
```

### 7.3 Daily P&L Check (Reference: Section 1.3, mtus:daily_pnl)
```bash
redis-cli GET mtus:daily_pnl
# Expected: Negative (loss) or positive (profit) SOL amount

# Verify daily loss limit not exceeded:
# Default: -0.002 SOL (Reference: Section 3.5)
```

---

## Phase 8: Go Live Checklist

### Final Verification Before Full Trading:

- [ ] All 98 Python tests pass (`python -m pytest`)
- [ ] TypeScript build succeeds (`npm run build`)
- [ ] Redis is running and accessible (`redis-cli ping` → PONG)
- [ ] `MTUS_ENVIRONMENT=production` in .env
- [ ] Sniper wallet balance ≥ 0.003 SOL
- [ ] All 11 agents start without errors
- [ ] Dashboard shows all agents as "healthy"
- [ ] Telegram bot responds to /status
- [ ] Test OTP verification works (/pause test)
- [ ] Priority queue is empty and accepting items
- [ ] Kill switch tested and working
- [ ] Dashboard WebSocket connected (ws://localhost:3001)
- [ ] Audit ledger recording events
- [ ] Position size set appropriately (start small: 0.0005 SOL)

---

## Monitoring During Live Trading:

1. **Dashboard**: http://localhost:3000 - Real-time overview
2. **Telegram**: Admin notifications for trades, TP/SL hits
3. **Redis CLI**: Monitor key metrics (mtus:daily_pnl, mtus:active_positions)
4. **Agent Logs**: Watch terminal outputs for errors
5. **Audit Ledger**: Periodic check of D:/Trader/data/positions.db

---

## Quick Reference: Agent Responsibilities (Reference: Section 2.2)

| Agent ID | Name | Responsibility |
|----------|------|----------------|
| AGT-01 | NOFX | Token detection (PumpDev/Whistle) |
| AGT-02 | Hermes | Event routing & queue processing |
| AGT-03 | Anansi | Safety qualification (G1-G11) |
| AGT-04 | Oracle | Price polling (Jupiter/DexScreener) |
| AGT-05 | Ares | Trade execution (Jupiter swap) |
| AGT-06 | Sentinel | TP/SL monitoring & position management |
| AGT-07 | Janus | Balance sweep & wallet management |
| AGT-08 | Cassandra | Social sentiment scoring |
| AGT-09 | Ledger | Audit ledger & event logging |
| AGT-10 | Heracles | Guardian & health monitoring |
| AGT-11 | DashboardBridge | WebSocket server for dashboard |

---

## Important Notes:

1. **Naming Conventions**: DO NOT change event types (`token_gradated`, `token_migrated`, etc.) - they are hardcoded across Python and TypeScript (Reference: Section 8.3)

2. **Redis Key Patterns**: All keys use `mtus:` prefix. Event log storage uses `event:` prefix. DO NOT rename without updating all references.

3. **Jupiter API Versions**: Different versions for different purposes (v1 for <$6 trades, v2 for ≥$6 trades, v3 for price queries). DO NOT change without understanding feature differences.

4. **Rate Limits**: Max 3 trades/hour, 1 concurrent position, daily loss limit -0.002 SOL (Reference: Section 3.5)

5. **Operational Window**: Trading only during configured hours (default 0-24) (Reference: Section 1.1)

---

**Ready to execute?** Review the checklist and confirm all items pass before starting live trading with larger position sizes.
