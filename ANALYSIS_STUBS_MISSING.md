# MTUS - Complete Analysis: Stubs, Missing & Mismatched

## 1. STUBS / PLACEHOLDER CODE (Empty Implementations)

| File | Location | Issue |
|------|----------|-------|
| `src/python/agents/oracle.py:102` | `pass` | Silent exception in Birdeye fallback |
| `src/python/agents/anansi.py:633` | `pass` | Silent exception in social data collection |
| `src/python/shared/telegram_bot.py:150` | `pass` | Silent exception in callback query |

**Analysis**: These are not stubs - they are silent exception handlers that swallow errors. This may cause silent failures.

---

## 2. AGENTS NOT IN PM2 (Running but not managed)

| Agent | File | Status |
|-------|------|--------|
| **Dashboard Bridge (AGT-11)** | `src/python/agents/dashboard_bridge.py` | NOT in ecosystem.config.js |
| **Tests** | Multiple test files | Not for production |

---

## 3. GATES NOT FULLY IMPLEMENTED (G3-G9)

Per `src/python/agents/anansi.py:437-446`:

```python
# Skip heavy API checks in paper mode but log intent
if self.is_paper_mode:
    print(f"AGT-03: [PAPER] Skipping G3-G6 API checks (would run in production)")
    gates_passed.extend(["G3", "G4", "G5", "G6"])
```

| Gate | Check | Implementation | Status |
|------|-------|----------------|--------|
| G1 | Mint Authority | ✅ Full via RugCheck | Working |
| G2 | Freeze Authority | ✅ Full via RugCheck | Working |
| G3 | LP Lock ≥85% | ⚠️ Requires rugcheck_api_key | Skipped in paper mode |
| G4 | Dev Holdings <5% | ⚠️ Requires RPC calls | Skipped in paper mode |
| G5 | Top 10 <30% | ⚠️ Requires RPC calls | Skipped in paper mode |
| G6 | RugCheck Score ≤300 | ⚠️ Requires rugcheck_api_key | Skipped in paper mode |
| G7 | Market Cap 5-150 SOL | ✅ Full | Working |
| G8 | Social Metadata | ❌ NOT called | Not implemented |
| G9 | Duplicate Check | ❌ NOT called | Not implemented |
| G10 | Honeypot | ✅ Basic check | Working |

---

## 4. MULTI-RPC BROADCAST NOT IMPLEMENTED

**Spec Section 3.5**: "Broadcast to all 3 RPCs simultaneously via Promise.allSettled"

**Current Implementation** (`src/typescript/agents/ares.ts:291`):
```typescript
const txId = await connection.sendRawTransaction(signedTxBytes, {
  skipPreflight: true,
  preflightCommitment: "processed"
});
```

**Issue**: Only uses single Helius RPC, not broadcasting to QuickNode + Alchemy.

---

## 5. FEATURES IN SHARED FOLDER BUT NOT IMPORTED

| File | Purpose | Imported By |
|------|---------|-------------|
| `src/python/shared/rpc_health.py` | Multi-RPC load balancer | ❌ NOT imported anywhere |
| `src/python/shared/rate_limiter.py` | Rate limiting | ❌ NOT imported anywhere |
| `src/python/shared/solana_simulator.py` | Honeypot detection | ❌ NOT imported anywhere |
| `src/python/shared/incident_response.py` | P0/P1 incidents | ❌ NOT imported anywhere |
| `src/python/shared/notification_templates.py` | Telegram templates | ❌ NOT imported anywhere |
| `src/python/shared/position_validator.py` | Position validation | ❌ NOT imported anywhere |
| `src/python/shared/rotating_logger.py` | Daily logs | ❌ NOT imported anywhere |
| `src/python/shared/validators.py` | Input validation | Only by token_payload.py |
| `src/python/shared/keystore.py` | Encrypted keystore | ❌ NOT imported anywhere |

---

## 6. ENVIRONMENT ISSUES

| Variable | Expected | Actual | Issue |
|----------|----------|--------|-------|
| `operational_window.start_hour_ist` | 21 | 0 | Should be 21:00 per spec |
| `operational_window.end_hour_ist` | 6 | 23 | Should be 06:00 per spec |
| `trading.max_simultaneous_positions` | 3 | 1 | Per spec should be 3 |
| `trading.max_trades_per_hour` | 10 | 5 | Per spec should be 10 |
| `trading.daily_loss_limit_sol` | 1.0 | 0.001 | Per spec should be 1.0 |

---

## 7. FILES IN ARCHIVE BUT NOT INTEGRATED

| File | Purpose |
|------|---------|
| `scripts/archive/start_all.ps1` | Complete system startup |
| `scripts/archive/test_paper_trading.py` | Paper trading verification |
| `scripts/archive/start_agents.py` | Agent startup script |
| `scripts/archive/start_mtus.sh` | Main startup script |

---

## 8. TELEGRAM BOT NOT CONNECTED

The `src/python/shared/telegram_bot.py` exists but is:
- NOT started by PM2
- NOT imported by any agent
- NOT receiving events from Heracles

---

## 9. DASHBOARD NOT RUNNING

- Dashboard folder exists at `D:\Trader\dashboard`
- Not started by PM2
- Dashboard Bridge exists but not running

---

## 10. CIRCULAR DEPENDENCY / IMPORT ISSUES

The LSP shows type errors in several files:
- `telegram_bot.py`: Type issues with Optional[str] vs str
- `hermes.py`: "publish" not known attribute of None
- `anansi.py`: "exists", "setex" not known attributes of None

These are type checking issues, not runtime issues.

---

## SUMMARY - PRIORITY FIXES

| Priority | Item | Location |
|----------|------|----------|
| HIGH | Add Dashboard Bridge (AGT-11) to PM2 | ecosystem.config.js |
| HIGH | Enable G3-G9 in production mode | anansi.py |
| HIGH | Implement multi-RPC broadcast | ares.ts |
| MEDIUM | Connect Telegram Bot to system | Need startup script |
| MEDIUM | Fix operational window hours | config/config.yaml |
| MEDIUM | Run Dashboard | dashboard/ |
| LOW | Integrate shared modules | Various |

---

## RUNNING SERVICES

### Currently Running (via PM2):
- nofx-radar (AGT-01)
- hermes-router (AGT-02)
- anansi-safety (AGT-03)
- oracle-price (AGT-04)
- ares-executor (AGT-05)
- sentinel-monitor (AGT-06)
- janus-sweep (AGT-07)
- cassandra-social (AGT-08)
- ledger-audit (AGT-09)
- heracles-guardian (AGT-10)

### NOT Running:
- Dashboard Bridge (AGT-11) - exists but not started
- Dashboard UI - exists but not started
- Telegram Bot - exists but not started