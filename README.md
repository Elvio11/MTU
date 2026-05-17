# MTUS (MemeTrader Unified System)

Enterprise-Grade Solana Meme Coin Sniper Bot.

## Overview

The MTUS is a multi-agent system built on an event-driven architecture using Redis as the message bus. The system detects new tokens, validates them through a 10-gate safety pipeline, executes trades via Jupiter, and monitors positions for take-profit/stop-loss conditions.

## Architecture

* **Event Bus:** Redis Pub/Sub (real-time inter-agent messages and Telegram notification broker)
* **Data Storage:** PostgreSQL (`mtus_db`) with pool-backed persistence (SQLite positions.db remains for sandbox/test environments)
* **Agents:** 11 distinct microservices spanning Python and TypeScript
* **Dashboard:** Next.js 16 (React + TypeScript) with WebSocket bridge

## Components

1. **AGT-01: NofxAgent (Token Radar)** - Connects to PumpDev/Whistle WebSocket to detect new token launches.
2. **AGT-02: HermesAgent (Event Router)** - Routes detected tokens to safety and sentiment analysis agents.
3. **AGT-03: AnansiAgent (Safety Gates)** - Executes a 10-gate safety qualification pipeline.
4. **AGT-04: Oracle (Price Polling)** - Polls token prices from Jupiter/DexScreener/Birdeye.
5. **AGT-05: Ares (Trade Executor)** - Executes Jupiter swaps, broadcasts to RPC.
6. **AGT-06: Sentinel (TP/SL Monitor)** - Monitors open positions, triggers TP/SL.
7. **AGT-08: CassandraAgent (Sentiment)** - Fetches social sentiment scores.
8. **AGT-09: LedgerAgent (Audit)** - Records trade events to PostgreSQL.
9. **AGT-10: HeraclesAgent (Guardian)** - Health monitoring, kill switch.
10. **AGT-11: DashboardBridge** - WebSocket server for the UI.

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Elvio11/MTU.git
   cd MTU
   ```

2. **Environment Variables:**
   Copy `.env.example` to `.env` and fill in the required keys:
   - RPC Providers (Helius, QuickNode, Alchemy)
   - Telegram Bot credentials
   - Redis URL
   - Wallet configuration

3. **Install Dependencies:**
   ```bash
   npm install
   pip install -r requirements.txt
   ```

4. **Start the System:**
   - Ensure Redis is running.
   - Run the startup scripts:
     ```bash
     npm run build
     python scripts/run_all_agents.py
     ```

## Configuration

The master configuration is located in `config/config.yaml`. It includes settings for:
- Trading windows
- Wallet thresholds
- Position sizing
- Rate limits

## Recent Production Updates (May 2026)

*   **Jupiter Price API V3 Migration**: Upgraded both `ares` (AGT-05) and `sentinel` (AGT-06) agents to use the latest stable Jupiter Price API V3 endpoint (`https://api.jup.ag/price/v3`). Updated price field resolutions from `.price` to `.usdPrice` to align with the new schema, resolving 401/404 errors.
*   **PostgreSQL Persistence Integration**: Standardized the system-wide storage on high-concurrency PostgreSQL (`mtus_db`) using `node-postgres` with pool-backed transaction safety. Open positions are dynamically queried on every monitoring tick.
*   **Live Sniper Verification**: Successfully validated and tested real-time trade executions via Jupiter CLI integration, ensuring automatic Position Open notifications are pushed to Redis and tracked continuously.

## Security

- Keys are encrypted using Argon2id + XSalsa20-Poly1305.
- Hardened safety pipeline (10-gates) before executing trades.
- Paper trading mode for testing execution flows without real funds.

## Documentation

For full technical details, refer to `TECHNICAL_DOCUMENTATION.md` and the generated `TECHNICAL_DOCUMENTATION.html`.
