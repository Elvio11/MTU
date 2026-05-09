'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useWebSocket } from '@/lib/websocket';
import { useBinance } from '@/lib/binance-websocket';
import { useAdmin } from '@/lib/admin-context';
import AgentCard from '@/components/AgentCard';
import PositionCard from '@/components/PositionCard';
import PnLChart from '@/components/PnLChart';
import PortfolioSummary from '@/components/PortfolioSummary';
import PriceTicker from '@/components/PriceTicker';
import MemeCoins from '@/components/MemeCoins';
import SystemStatus from '@/components/SystemStatus';
import { TrendingUp, Activity, Wifi, WifiOff } from 'lucide-react';

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

interface EnvelopePayload {
  envelope_id: string;
  agent_id: string;
  event_type: string;
  timestamp_utc: string;
  payload: {
    status?: string;
    daily_pnl?: number;
    [key: string]: unknown;
  };
  correlation_id: string;
  schema_version: string;
}

interface PositionOpenedPayload {
  position_id: string;
  mint: string;
  symbol?: string;
  entry_price_sol: number;
  quantity?: number;
}

interface PositionClosedPayload {
  position_id: string;
  realised_pnl_sol?: number;
}

interface SystemAlert {
  level: string;
  message: string;
  timestamp?: string;
}

interface PriceUpdatedPayload {
  mint: string;
  price_sol: number;
  timestamp: number;
}

interface TPHitPayload {
  position_id: string;
  token: string;
  pnl_sol: number;
  reason: string;
}

interface KillSwitchPayload {
  reason: string;
  timestamp: number;
}

export default function HomePage() {
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [pnlTotal, setPnlTotal] = useState(0);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [tradingPaused, setTradingPaused] = useState(false);
  const [systemAlerts, setSystemAlerts] = useState<SystemAlert[]>([]);
  const ws = useWebSocket();
  const { tickers: binanceTickers, connected: binanceConnected, refreshStats } = useBinance();
  const { isAdminMode } = useAdmin();

  useEffect(() => {
    if (binanceConnected && binanceTickers.size > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLastUpdate(new Date());
    }
  }, [binanceConnected, binanceTickers]);

  useEffect(() => {
    refreshStats();
    const interval = setInterval(refreshStats, 60000);
    return () => clearInterval(interval);
  }, [refreshStats]);

  useEffect(() => {
    if (!ws) return;

    const handleAgentHealth = (payload: unknown) => {
      if (!payload || typeof payload !== 'object') return;
      
      const data = payload as Record<string, unknown>;
      const agentId = data.agent_id as string;
      if (!agentId) return;
      
      const rawStatus = (data.payload as Record<string, unknown>)?.status as string | undefined;
      const status: 'healthy' | 'unhealthy' = rawStatus === 'healthy' ? 'healthy' : 'unhealthy';
      
      setAgents(prev => {
        const payloadData = data.payload as Record<string, unknown>;
        const dailyPnl = payloadData?.daily_pnl as number | undefined;
        
        const existing = prev.find(a => a.id === agentId);
        const newAgents = existing
          ? prev.map(a => a.id === agentId ? { ...a, status, lastHeartbeat: '0s ago', pnlToday: dailyPnl } : a)
          : [...prev, { id: agentId, name: agentId, status, lastHeartbeat: '0s ago', tradesToday: 0, pnlToday: dailyPnl }];
        
        console.log('[health_check] setAgents:', JSON.stringify(newAgents));
        return newAgents;
      });
    };

    const handlePositionOpened = (payload: unknown) => {
      const data = payload as PositionOpenedPayload;
      setPositions(prev => [...prev, {
        positionId: data.position_id,
        mint: data.mint,
        symbol: data.symbol || 'TOKEN',
        entryPrice: data.entry_price_sol,
        currentPrice: data.entry_price_sol,
        pnl: 0,
        pnlPct: 0,
        state: 'OPEN',
        quantity: data.quantity || 0,
      }]);
    };

    const handlePositionClosed = (payload: unknown) => {
      const data = payload as PositionClosedPayload;
      setPositions(prev => prev.filter(p => p.positionId !== data.position_id));
      const pnl = data.realised_pnl_sol;
      if (pnl !== undefined) {
        setPnlTotal(prev => prev + pnl);
      }
    };

    const handleSystemAlert = (payload: unknown) => {
      const data = payload as SystemAlert;
      setSystemAlerts(prev => [
        { ...data, timestamp: new Date().toISOString() },
        ...prev.slice(0, 9)
      ]);
    };

    const handlePriceUpdated = (payload: unknown) => {
      const data = payload as PriceUpdatedPayload;
      setPositions(prev => prev.map(p => 
        p.mint === data.mint 
          ? { 
              ...p, 
              currentPrice: data.price_sol,
              pnl: (data.price_sol - p.entryPrice) * p.quantity,
              pnlPct: ((data.price_sol - p.entryPrice) / p.entryPrice) * 100
            }
          : p
      ));
    };

    const handleTP1Hit = (payload: unknown) => {
      const data = payload as TPHitPayload;
      setSystemAlerts(prev => [
        { level: 'INFO', message: `🎯 TP1 Hit: ${data.token} PnL: ${data.pnl_sol.toFixed(4)} SOL`, timestamp: new Date().toISOString() },
        ...prev.slice(0, 9)
      ]);
    };

    const handleTP2Hit = (payload: unknown) => {
      const data = payload as TPHitPayload;
      setSystemAlerts(prev => [
        { level: 'INFO', message: `🎯 TP2 Hit: ${data.token} PnL: ${data.pnl_sol.toFixed(4)} SOL`, timestamp: new Date().toISOString() },
        ...prev.slice(0, 9)
      ]);
    };

    const handleStopLoss = (payload: unknown) => {
      const data = payload as TPHitPayload;
      setSystemAlerts(prev => [
        { level: 'ERROR', message: `🛑 Stop Loss: ${data.token} PnL: ${data.pnl_sol.toFixed(4)} SOL`, timestamp: new Date().toISOString() },
        ...prev.slice(0, 9)
      ]);
    };

    const handleKillSwitch = (payload: unknown) => {
      const data = payload as KillSwitchPayload;
      setTradingPaused(true);
      setSystemAlerts(prev => [
        { level: 'CRITICAL', message: `🚨 KILLSWITCH TRIGGERED: ${data.reason}`, timestamp: new Date().toISOString() },
        ...prev.slice(0, 9)
      ]);
    };

    ws.subscribe('health_check', handleAgentHealth);
    ws.subscribe('position_opened', handlePositionOpened);
    ws.subscribe('position_closed', handlePositionClosed);
    ws.subscribe('system_alert', handleSystemAlert);
    ws.subscribe('price_updated', handlePriceUpdated);
    ws.subscribe('tp1_hit', handleTP1Hit);
    ws.subscribe('tp2_hit', handleTP2Hit);
    ws.subscribe('stop_loss', handleStopLoss);
    ws.subscribe('kill_switch_triggered', handleKillSwitch);

    return () => {
      ws.unsubscribe('health_check', handleAgentHealth);
      ws.unsubscribe('position_opened', handlePositionOpened);
      ws.unsubscribe('position_closed', handlePositionClosed);
      ws.unsubscribe('system_alert', handleSystemAlert);
      ws.unsubscribe('price_updated', handlePriceUpdated);
      ws.unsubscribe('tp1_hit', handleTP1Hit);
      ws.unsubscribe('tp2_hit', handleTP2Hit);
      ws.unsubscribe('stop_loss', handleStopLoss);
      ws.unsubscribe('kill_switch_triggered', handleKillSwitch);
    };
  }, [ws]);

  const handlePauseTrading = useCallback(() => {
    ws?.send({ type: 'command', action: 'pause' });
    setTradingPaused(true);
  }, [ws]);

  const handleResumeTrading = useCallback(() => {
    ws?.send({ type: 'command', action: 'resume' });
    setTradingPaused(false);
  }, [ws]);

  const handleKillswitch = useCallback(() => {
    if (!isAdminMode) {
      alert('Admin mode required. Enable it in Settings first.');
      return;
    }
    if (confirm('Are you sure you want to trigger killswitch? All positions will be closed.')) {
      ws?.send({ type: 'command', action: 'killswitch' });
      setTradingPaused(true);
    }
  }, [ws, isAdminMode]);

  const totalValue = useMemo(() => positions.reduce((sum, p) => sum + (p.currentPrice * p.quantity), 0), [positions]);
  const openPositions = useMemo(() => positions.filter(p => p.state === 'OPEN').length, [positions]);

  const binanceArray = useMemo(() => 
    Array.from(binanceTickers.values()).sort((a, b) => b.changePercent24h - a.changePercent24h), 
    [binanceTickers]
  );
  const topGainers = useMemo(() => binanceArray.slice(0, 5), [binanceArray]);
  const topVolume = useMemo(() => binanceArray.slice(0, 5), [binanceArray]);

  return (
    <div className="space-y-6">
      {/* Header with Portfolio Summary */}
      <PortfolioSummary 
        pnlTotal={pnlTotal}
        totalValue={totalValue}
        openPositions={openPositions}
        agentsCount={agents.length}
        connected={ws?.connected ?? false}
        lastUpdate={lastUpdate}
        onRefresh={() => {}}
        binanceConnected={binanceConnected}
      />

      {/* Connection Status Bar */}
      <div className="bg-mtus-card rounded-xl p-3 border border-slate-700">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {binanceConnected ? (
                <Wifi className="text-profit" size={16} />
              ) : (
                <WifiOff className="text-loss" size={16} />
              )}
              <span className="text-sm text-slate-400">
                Binance Live: <span className={binanceConnected ? 'text-profit' : 'text-loss'}>
                  {binanceConnected ? 'Connected' : 'Disconnected'}
                </span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              {ws?.connected ? (
                <Wifi className="text-profit" size={16} />
              ) : (
                <WifiOff className="text-loss" size={16} />
              )}
              <span className="text-sm text-slate-400">
                WebSocket: <span className={ws?.connected ? 'text-profit' : 'text-loss'}>
                  {ws?.connected ? 'Connected' : 'Disconnected'}
                </span>
              </span>
            </div>
          </div>
          {lastUpdate && (
            <span className="text-xs text-slate-500">
              Last update: {lastUpdate.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {/* Market Stats Bar */}
      <div className="bg-mtus-card rounded-xl p-4 border border-slate-700">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="text-profit" size={18} />
              <span className="text-slate-400 text-sm">Top Gainers (24h)</span>
            </div>
            <div className="flex gap-2">
              {topGainers.slice(0, 3).map(coin => (
                <span key={coin.symbol} className="text-sm font-medium text-white bg-slate-700 px-2 py-1 rounded">
                  {coin.symbol} <span className="text-profit">+{coin.changePercent24h.toFixed(1)}%</span>
                </span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <Activity className="text-mtus-accent" size={18} />
              <span className="text-slate-400 text-sm">Live Prices</span>
            </div>
            <div className="flex gap-2">
              {topVolume.slice(0, 3).map(coin => (
                <span key={coin.symbol} className="text-sm font-medium text-white bg-slate-700 px-2 py-1 rounded">
                  {coin.symbol} <span className="text-slate-400">${coin.price.toFixed(2)}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Live Market Prices - Horizontal Button Layout */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-lg font-semibold text-slate-300">Live Prices</h2>
          <div className="flex items-center gap-1">
            <span className={`w-2 h-2 rounded-full ${binanceConnected ? 'bg-profit' : 'bg-loss'}`} />
            <span className="text-xs text-slate-500">{binanceConnected ? 'Binance' : 'Offline'}</span>
          </div>
        </div>
        
        {binanceConnected && binanceArray.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2">
            {binanceArray.map((coin) => (
              <PriceTicker
                key={coin.symbol}
                symbol={coin.symbol}
                ticker={binanceTickers.get(coin.symbol)}
              />
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-slate-500">
            <WifiOff size={16} />
            <span>Connecting to price feed...</span>
          </div>
        )}
      </section>

      {/* Trending Meme Coins on Solana */}
      <MemeCoins />

      

      {/* Agents Status */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-slate-300">Trading Agents</h2>
          <span className="text-sm text-slate-400">{agents.length} active</span>
        </div>
        {agents.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {agents.map(agent => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-slate-500 bg-mtus-card rounded-xl border border-slate-700">
            <p>No agents connected</p>
            <p className="text-sm mt-2">Waiting for agent health updates...</p>
          </div>
        )}
      </section>

      {/* System Alerts / Telegram */}
      {systemAlerts.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-slate-300">Telegram Alerts</h2>
            <span className="text-sm text-slate-400">{systemAlerts.length} alerts</span>
          </div>
          <div className="space-y-2">
            {systemAlerts.map((alert, idx) => (
              <div 
                key={idx} 
                className={`p-3 rounded-lg border ${
                  alert.level === 'CRITICAL' ? 'bg-red-900/20 border-red-700' :
                  alert.level === 'ERROR' ? 'bg-orange-900/20 border-orange-700' :
                  alert.level === 'WARN' ? 'bg-yellow-900/20 border-yellow-700' :
                  'bg-mtus-card border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium ${
                    alert.level === 'CRITICAL' ? 'text-red-400' :
                    alert.level === 'ERROR' ? 'text-orange-400' :
                    alert.level === 'WARN' ? 'text-yellow-400' :
                    'text-blue-400'
                  }`}>
                    {alert.level}: {alert.message}
                  </span>
                  {alert.timestamp && (
                    <span className="text-xs text-slate-500">
                      {new Date(alert.timestamp).toLocaleTimeString()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Open Positions */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-slate-300">Open Positions</h2>
          <span className="text-sm text-slate-400">{openPositions} positions</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {positions.filter(p => p.state === 'OPEN').map(pos => (
            <PositionCard key={pos.positionId} position={pos} />
          ))}
          {openPositions === 0 && (
            <div className="col-span-full text-center py-8 text-slate-500 bg-mtus-card rounded-xl border border-slate-700">
              <p>No open positions</p>
            </div>
          )}
        </div>
      </section>

      {/* PnL Chart */}
      <section>
        <h2 className="text-lg font-semibold mb-3 text-slate-300">PnL History (24h)</h2>
        <PnLChart />
      </section>

      {/* System Status - RPC, Circuit Breakers, Rate Limiter */}
      <section>
        <h2 className="text-lg font-semibold mb-3 text-slate-300">System Status</h2>
        <SystemStatus />
      </section>

      {/* Control Panel */}
      <section className="flex flex-wrap gap-3 pt-4 border-t border-slate-700">
        <button 
          className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          onClick={handlePauseTrading}
          disabled={!ws?.connected || tradingPaused}
        >
          Pause Trading
        </button>
        <button 
          className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          onClick={handleResumeTrading}
          disabled={!ws?.connected || !tradingPaused}
        >
          Resume Trading
        </button>
        <button 
          className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          onClick={handleKillswitch}
          disabled={!ws?.connected}
        >
          Killswitch
        </button>
      </section>
    </div>
  );
}