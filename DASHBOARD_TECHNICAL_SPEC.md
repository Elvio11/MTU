# MTUS Dashboard Technical Specification v1.0.0

---

## **SECTION 1: EXECUTIVE SUMMARY**

### 1.1 Purpose
The MTUS Dashboard serves as the primary monitoring and control interface for the Multi-Token Trading System. It provides real-time visibility into trading operations, agent health, positions, and system alerts through a web-based UI connected via WebSocket to the Python agent infrastructure.

### 1.2 Current State Assessment

| Component | Status | Coverage |
|-----------|--------|----------|
| WebSocket Connection | ✅ Working | 80% |
| Binance Price Feed | ✅ Working (with fallback) | 70% |
| Agent Monitoring | ✅ Basic | 50% |
| Position Tracking | ✅ Basic | 60% |
| Trade History | ❌ Not implemented | 0% |
| PnL Charts | ❌ Placeholder | 0% |
| Telegram Integration | ❌ Not connected | 0% |
| RPC Health Monitoring | ❌ Not implemented | 0% |
| Circuit Breaker Status | ❌ Not implemented | 0% |
| Rate Limiter Status | ❌ Not implemented | 0% |
| Settings/Configuration | ❌ Not implemented | 0% |

### 1.3 Target Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        MTUS Dashboard                           │
├─────────────────────────────────────────────────────────────────┤
│  L1: Presentation Layer (Next.js 16 - React 19)                 │
│  ├── Pages: Dashboard, Positions, Agents, History, Settings      │
│  └── Components: Cards, Charts, Forms, Tables                  │
├─────────────────────────────────────────────────────────────────┤
│  L2: State Management (React Context + WebSocket)              │
│  ├── WebSocketProvider - Real-time message bus                 │
│  ├── BinanceProvider - Crypto price feeds                      │
│  └── AgentStateProvider - Agent health tracking                │
├─────────────────────────────────────────────────────────────────┤
│  L3: Data Integration Layer                                     │
│  ├── Redis Pub/Sub (via dashboard_bridge.py)                   │
│  ├── REST API endpoints (future)                                │
│  └── Local Storage (settings, preferences)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## **SECTION 2: DASHBOARD PAGES & FEATURES**

### 2.1 Dashboard Page (Main) - `/`

#### Current Features
- Portfolio Summary (PnL, Total Value, Open Positions, Active Agents)
- Connection Status Bar (WebSocket, Binance)
- Market Stats Bar (Top Gainers, Live Prices)
- Live Price Tickers (from Binance)
- Trending Meme Coins section (placeholder)
- Agent Status Cards
- System Alerts panel
- Open Positions Grid
- PnL History Chart (placeholder)
- Control Panel (Pause, Resume, Killswitch buttons)

#### Gaps Identified
- [ ] No historical PnL data - chart is empty
- [ ] Meme coins section shows "Loading..." - no data source
- [ ] Control panel buttons not wired to actual commands
- [ ] No error handling for failed WebSocket reconnection
- [ ] No manual refresh for Binance data
- [ ] No filter/sort for positions

#### Recommended Enhancements
- Connect to Ledger agent for historical PnL data
- Add PumpPortal API integration for Solana meme coins
- Wire control buttons to Telegram commands via WebSocket
- Implement exponential backoff for WebSocket retries
- Add pull-to-refresh for market data
- Add position filtering (by state, token, date)

### 2.2 Positions Page - `/positions`

#### Current Features
- Grid of position cards
- Open/Closed section separation
- Basic position display (ID, symbol, entry, current, PnL)

#### Gaps Identified
- [ ] No real-time price updates for open positions
- [ ] No TP/SL indicators on position cards
- [ ] No position details modal
- [ ] No exit position functionality
- [ ] No position history with entry/exit timestamps
- [ ] No position notes/tags

#### Recommended Enhancements
- Subscribe to price_updated events for real-time PnL
- Add visual TP1/TP2/SL markers on position cards
- Implement position detail drawer with full history
- Add manual exit button (sends to Telegram for approval)
- Store position history in localStorage for persistence
- Add custom tags/notes for manual trade journaling

### 2.3 Agents Page - `/agents`

#### Current Features
- Agent health status display
- Healthy/Unhealthy/Other sections
- Agent cards with status indicator

#### Gaps Identified
- [ ] No detailed agent metrics
- [ ] No agent-specific PnL
- [ ] No restart/reload agent controls
- [ ] No agent logs viewer
- [ ] No configuration for agent parameters

#### Recommended Enhancements
- Add detailed metrics per agent (trades/day, avg hold time, win rate)
- Show agent-specific daily PnL
- Add restart button with confirmation
- Add log viewer modal with search/filter
- Add agent parameter configuration panel
- Show agent message throughput stats

### 2.4 History Page - `/history`

#### Current Features
- Empty page (no implementation)

#### Recommended Features
- Trade history table with all closed positions
- Date range filter
- Export to CSV/JSON
- PnL summary statistics
- Win/Loss ratio chart
- Average trade duration
- Best/worst trades highlight

### 2.5 Settings Page - `/settings`

#### Current Features
- Empty page placeholder

#### Recommended Features
- **Connection Settings**
  - WebSocket URL configuration
  - Reconnection attempts limit
  - Reconnection interval
  
- **Display Settings**
  - Theme (dark/light/system)
  - Number format (decimal separators)
  - Language (en/es/ko/etc)
  - Dashboard refresh rate
  
- **Notification Settings**
  - Telegram bot link
  - Email alerts toggle
  - Push notification preferences
  
- **Trading Parameters** (read-only display)
  - Max position size
  - Max concurrent positions
  - Daily loss limit
  - TP1/TP2/SL percentages

---

## **SECTION 3: DATA INTEGRATION**

### 3.1 WebSocket Message Types

#### Currently Subscribed
| Channel | Handler | Status |
|---------|---------|--------|
| health_check | handleAgentHealth | ✅ Working |
| position_opened | handlePositionOpened | ✅ Working |
| position_closed | handlePositionClosed | ✅ Working |
| system_alert | handleSystemAlert | ✅ Working |

#### Recommended Additions
| Channel | Purpose | Priority |
|---------|---------|----------|
| price_updated | Real-time position PnL | HIGH |
| tp1_hit | Take Profit 1 notifications | HIGH |
| tp2_hit | Take Profit 2 notifications | HIGH |
| stop_loss | Stop Loss notifications | HIGH |
| token_qualified | New token alerts | MEDIUM |
| trade_executed | Trade confirmation | MEDIUM |
| rpc_status | RPC health status | MEDIUM |
| circuit_breaker | Circuit breaker state | MEDIUM |
| rate_limit | Rate limiter status | LOW |
| daily_summary | Daily PnL summary | LOW |

### 3.2 Redis Channels to Dashboard Bridge

#### Current Channels
- position_opened ✅
- position_closed ✅
- price_updated ✅
- health_check ✅
- system_alert ✅
- kill_switch_triggered ✅

#### Missing Channels
| Channel | Purpose | Priority |
|---------|---------|----------|
| token_qualified | New token detected | MEDIUM |
| trade_approved | Trade approved | MEDIUM |
| trade_executed | Trade executed | MEDIUM |
| tp1_hit | TP1 reached | HIGH |
| tp2_hit | TP2 reached | HIGH |
| stop_loss_hit | SL triggered | HIGH |
| daily_pnl_update | Periodic PnL update | MEDIUM |
| rpc_health | RPC status updates | MEDIUM |
| circuit_state | Circuit breaker state | LOW |
| rate_limit_status | Rate limiter state | LOW |

### 3.3 API Integrations

#### Current
- **Binance REST API** - 24h ticker data ✅
- **Binance WebSocket** - Real-time trades ✅
- **Fallback Data** - Static ticker data ✅

#### Recommended
- **PumpPortal WebSocket** - New Solana tokens
- **DexScreener API** - Token price/ liquidity data
- **Birdeye API** - Additional price data
- **Jupiter API** - Token metadata
- **RugCheck API** - Safety scores display

---

## **SECTION 4: COMPONENT ARCHITECTURE**

### 4.1 Provider Hierarchy

```
App
├── WebSocketProvider (context: ws, subscribe, unsubscribe, connected)
├── BinanceProvider (context: tickers, connected, refreshStats)
├── SettingsProvider (context: theme, language, preferences)
└── Children
    ├── Layout
    │   └── Sidebar
    └── Pages
        ├── DashboardPage
        ├── PositionsPage
        ├── AgentsPage
        ├── HistoryPage
        └── SettingsPage
```

### 4.2 Custom Hooks

#### Existing
- `useWebSocket()` - WebSocket connection and messaging
- `useBinance()` - Binance price data
- `useBinanceTicker(symbol)` - Individual ticker data

#### Recommended
- `useAgent(agentId)` - Single agent data
- `usePosition(positionId)` - Single position data
- `useTradeHistory(filters)` - Historical trades
- `usePnLStats(period)` - PnL statistics
- `useSystemStatus()` - Overall system health
- `useRPCStatus()` - RPC endpoint health
- `useRateLimiter()` - Rate limiter state
- `useSettings()` - User preferences

### 4.3 Data Models

#### Current Interfaces
```typescript
interface AgentStatus {
  id: string;
  name: string;
  status: 'healthy' | 'unhealthy' | 'starting' | 'paused';
  lastHeartbeat: string;
  tradesToday: number;
  pnlToday?: number;
}

interface Position {
  positionId: string;
  mint: string;
  symbol: string;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  pnlPct: number;
  state: string;
  quantity: number;
}
```

#### Recommended Additions
```typescript
interface TradeRecord {
  id: string;
  positionId: string;
  token: string;
  entryTime: Date;
  exitTime?: Date;
  entryPrice: number;
  exitPrice?: number;
  quantity: number;
  pnl: number;
  pnlPct: number;
  exitReason: 'tp1' | 'tp2' | 'sl' | 'manual' | 'time';
  fees: number;
}

interface RPCStatus {
  helius: { state: 'closed' | 'open' | 'half_open'; failures: number };
  quicknode: { state: 'closed' | 'open' | 'half_open'; failures: number };
  alchemy: { state: 'closed' | 'open' | 'half_open'; failures: number };
}

interface RateLimiterStatus {
  tradesThisHour: number;
  maxTradesPerHour: number;
  activePositions: number;
  maxPositions: number;
  canTrade: boolean;
}

interface AgentMetrics {
  id: string;
  name: string;
  uptime: number;
  messagesProcessed: number;
  errors: number;
  lastError?: string;
  avgResponseTime: number;
}

interface SystemAlert {
  id: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL';
  message: string;
  timestamp: Date;
  source: string;
  acknowledged: boolean;
}
```

---

## **SECTION 5: SECURITY & AUTHENTICATION**

### 5.1 Current State
- No authentication required (internal tool)
- WebSocket connection open to localhost:3001
- No encryption on WS messages

### 5.2 Recommended Security

| Feature | Implementation | Priority |
|---------|---------------|----------|
| Admin Mode | Read-only by default, write via OTP | HIGH |
| WebSocket Auth | Token-based authentication | MEDIUM |
| Rate Limiting | Client-side message rate limit | LOW |
| Input Sanitization | Validate all WS messages | HIGH |
| Session Timeout | Auto-logout after inactivity | MEDIUM |

---

## **SECTION 6: PERFORMANCE OPTIMIZATION**

### 6.1 Current Issues
- WebSocket reconnects every 3 seconds on failure (no backoff)
- Binance data updates every 1s (excessive)
- No data caching
- No pagination for large lists

### 6.2 Recommendations

| Optimization | Implementation | Impact |
|--------------|---------------|--------|
| Message Batching | Batch WS updates in 100ms window | Reduce re-renders |
| Virtual Scrolling | Use react-window for large lists | Memory usage |
| Data Caching | Cache price data, invalidate on update | API calls |
| Pagination | Lazy load history data | Initial load time |
| Debounced Updates | Debounce price updates to 1s | CPU usage |
| Service Worker | Cache static assets | Load time |

---

## **SECTION 7: ERROR HANDLING & MONITORING**

### 7.1 Current Gaps
- No error boundaries
- No offline indicator
- No retry mechanism for failed data fetches
- No error logging

### 7.2 Recommended Implementation

```typescript
// Error Boundary Component
class DashboardErrorBoundary extends React.Component {
  state = { hasError: false, error: null };
  
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  
  render() {
    if (this.state.hasError) {
      return <ErrorFallback error={this.state.error} />;
    }
    return this.props.children;
  }
}

// Offline Detection
function useNetworkStatus() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);
  return online;
}
```

---

## **SECTION 8: MOBILE & RESPONSIVE DESIGN**

### 8.1 Current State
- Basic responsive grid (mobile/tablet/desktop breakpoints)
- Cards stack on mobile
- No touch-optimized controls

### 8.2 Recommendations

| Feature | Implementation | Priority |
|---------|---------------|----------|
| Mobile Navigation | Bottom tab bar for mobile | MEDIUM |
| Touch Gestures | Swipe to dismiss alerts | LOW |
| PWA Support | Service worker, manifest | MEDIUM |
| Dark Mode | System preference detection | HIGH |
| Reduced Motion | Respect OS animation settings | LOW |

---

## **SECTION 9: TESTING STRATEGY**

### 9.1 Current Testing
- None implemented

### 9.2 Recommended Testing

| Test Type | Coverage Target | Tools |
|-----------|-----------------|-------|
| Unit Tests | ≥80% components | Vitest + React Testing Library |
| Integration Tests | ≥50% flows | Playwright |
| E2E Tests | Critical paths | Playwright |
| Performance Tests | Bundle size < 500KB | Lighthouse |
| Accessibility | WCAG 2.1 AA | axe-core |

### 9.3 Critical Test Cases

1. **WebSocket Reconnection**
   - Simulate network loss
   - Verify auto-reconnect with backoff
   - Verify message queue during reconnect

2. **Price Feed Updates**
   - Handle rapid updates without lag
   - Handle stale data gracefully

3. **Position State Transitions**
   - Open → TP1 → TP2 → Closed
   - Open → SL → Closed
   - Open → Manual Exit

4. **Agent Health Updates**
   - Show healthy/unhealthy transitions
   - Handle missing agent data

5. **Error States**
   - WebSocket disconnection
   - Binance API failure
   - Invalid message format

---

## **SECTION 10: DEPLOYMENT & INFRASTRUCTURE**

### 10.1 Current Setup
- Development: `npm run dev` (Next.js 16 dev server)
- Production: `npm run build && npm run start`
- No Docker containerization

### 10.2 Recommended Deployment

```yaml
# docker-compose.yml
version: '3.8'
services:
  dashboard:
    build: ./dashboard
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - NEXT_PUBLIC_WS_URL=ws://dashboard-bridge:3001
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 10.3 Environment Variables

| Variable | Current | Required |
|----------|---------|----------|
| NODE_ENV | development | Yes |
| NEXT_PUBLIC_WS_URL | ws://localhost:3001 | Yes |
| NEXT_PUBLIC_BINANCE_WS | wss://stream.binance.com:9443/ws | Yes |
| NEXT_PUBLIC_BINANCE_API | https://api.binance.com/api/v3 | Yes |

---

## **SECTION 11: IMPLEMENTATION ROADMAP**

### Phase 1: Core Functionality (Week 1)
- [ ] Fix WebSocket reconnection with exponential backoff
- [ ] Add price_updated event subscription for real-time PnL
- [ ] Wire control buttons to actual commands
- [ ] Add error boundaries and offline detection

### Phase 2: Data & History (Week 2)
- [ ] Connect to Ledger agent for trade history
- [ ] Implement History page with filters
- [ ] Add PnL statistics and charts
- [ ] Export functionality (CSV/JSON)

### Phase 3: Enhanced Monitoring (Week 3)
- [ ] Add RPC health status display
- [ ] Add circuit breaker status
- [ ] Add rate limiter status
- [ ] Agent metrics dashboard

### Phase 4: User Experience (Week 4)
- [ ] Settings page implementation
- [ ] Theme toggle (dark/light)
- [ ] Mobile-responsive improvements
- [ ] PWA support

### Phase 5: Polish & Security (Week 5)
- [ ] Admin mode with OTP
- [ ] WebSocket authentication
- [ ] Performance optimization
- [ ] Comprehensive testing

---

## **SECTION 12: DEPENDENCIES**

### 12.1 Current Dependencies
```json
{
  "next": "^16.2.4",
  "react": "^19.0.0",
  "react-dom": "^19.0.0",
  "typescript": "^5.0.0",
  "tailwindcss": "^4.0.0",
  "lucide-react": "^0.400.0",
  "recharts": "^2.12.0",
  "clsx": "^2.1.0",
  "ws": "^8.16.0",
  "zod": "^4.0.0"
}
```

### 12.2 Recommended Additions
```json
{
  "@tanstack/react-query": "^5.0.0",
  "zustand": "^4.5.0",
  "date-fns": "^3.0.0",
  "react-hook-form": "^7.50.0",
  "@hookform/resolvers": "^3.3.0",
  "react-router-dom": "^6.22.0",
  "framer-motion": "^11.0.0",
  "@tanstack/react-virtual": "^3.0.0",
  "sonner": "^1.4.0",
  "zustand-persist": "^1.0.0"
}
```

---

## **SECTION 13: OPEN QUESTIONS & DECISIONS NEEDED**

1. **Data Persistence**: Should trade history be stored in browser (localStorage/IndexedDB) or fetched from backend?
2. **Authentication**: Is admin authentication required for dashboard, or is it internal-only?
3. **Multi-instance**: Will there be multiple trading instances (paper/live)? How to handle switching?
4. **Alert Sounds**: Should there be audio alerts for TP/SL triggers?
5. **Custom Indicators**: Should users be able to add custom price alerts?
6. **Widget Layout**: Should users be able to customize dashboard layout?
7. **Mobile App**: Is a native mobile app needed, or is responsive web sufficient?
8. **API Rate Limits**: How to handle dashboard API rate limits vs trading limits?

---

## **SUMMARY**

| Category | Current | Target | Gap |
|----------|---------|--------|-----|
| Real-time Data | 40% | 90% | Need more WS channels |
| Historical Data | 0% | 80% | Not implemented |
| Agent Monitoring | 50% | 100% | Missing metrics |
| Position Tracking | 60% | 100% | No real-time updates |
| Charts & Analytics | 10% | 80% | Not implemented |
| Settings/Config | 0% | 70% | Not implemented |
| Security | 0% | 60% | No auth |

**Estimated Implementation Time**: 5-6 weeks (full feature set)

---

## **APPENDIX A: FILE STRUCTURE**

```
dashboard/
├── src/
│   ├── app/
│   │   ├── page.tsx                    # Dashboard
│   │   ├── positions/page.tsx          # Positions
│   │   ├── agents/page.tsx             # Agents
│   │   ├── history/page.tsx             # History (TODO)
│   │   ├── settings/page.tsx            # Settings (TODO)
│   │   ├── layout.tsx                   # Root layout
│   │   ├── providers.tsx                 # Context providers
│   │   └── globals.css                  # Global styles
│   ├── components/
│   │   ├── Sidebar.tsx                  # Navigation
│   │   ├── AgentCard.tsx                # Agent display
│   │   ├── PositionCard.tsx             # Position display
│   │   ├── PnLChart.tsx                 # PnL visualization
│   │   ├── PortfolioSummary.tsx         # Portfolio overview
│   │   ├── PriceTicker.tsx              # Price display
│   │   ├── MarketTicker.tsx             # Market overview
│   │   ├── MemeCoins.tsx                 # Trending tokens
│   │   └── ... (more components)
│   └── lib/
│       ├── websocket.tsx               # WS provider
│       ├── binance-websocket.tsx        # Binance provider
│       ├── market.ts                    # Market data utils
│       ├── meme-coins.tsx               # Meme coin utils
│       └── ... (more utilities)
├── public/
│   └── ... (static assets)
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── next.config.js
```

---

## **APPENDIX B: MESSAGE FORMAT REFERENCE**

```typescript
// Agent Health Envelope
{
  "type": "health_check",
  "payload": {
    "envelope_id": "uuid",
    "agent_id": "AGT-10",
    "event_type": "health_check",
    "timestamp_utc": "2026-05-05T12:00:00Z",
    "payload": {
      "status": "healthy",
      "daily_pnl": 0.5
    },
    "correlation_id": "uuid",
    "schema_version": "1.0.0"
  }
}

// Position Opened
{
  "type": "position_opened",
  "payload": {
    "position_id": "pos_123",
    "mint": "_TOKEN_ADDRESS_",
    "symbol": "PEPE",
    "entry_price_sol": 0.015,
    "quantity": 1000
  }
}

// Price Updated
{
  "type": "price_updated",
  "payload": {
    "mint": "_TOKEN_ADDRESS_",
    "price_sol": 0.018,
    "timestamp": 1715000000
  }
}
```

---

*Document Version: 1.0.0*  
*Last Updated: May 5, 2026*  
*Author: Technical Specification - Dashboard Enhancement*