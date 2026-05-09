'use client';

import { useEffect, useState, useMemo } from 'react';
import { useWebSocket } from '@/lib/websocket';
import { Download, Filter, TrendingUp, TrendingDown, Clock, DollarSign } from 'lucide-react';

interface TradeRecord {
  id: string;
  positionId: string;
  symbol: string;
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  pnl: number;
  pnlPct: number;
  exitReason: 'tp1' | 'tp2' | 'sl' | 'manual' | 'time';
  entryTime: string;
  exitTime: string;
  fees: number;
}

interface PositionClosedPayload {
  position_id: string;
  realised_pnl_sol?: number;
  exit_price?: number;
  exit_reason?: string;
  symbol?: string;
  quantity?: number;
  entry_price_sol?: number;
}

export default function HistoryPage() {
  const [trades, setTrades] = useState<TradeRecord[]>(() => {
    if (typeof window === 'undefined') return [];
    const stored = localStorage.getItem('mtus_trade_history');
    if (!stored) return [];
    try {
      return JSON.parse(stored) as TradeRecord[];
    } catch {
      return [];
    }
  });
  const [filter, setFilter] = useState<'all' | 'win' | 'loss'>('all');
  const [dateRange, setDateRange] = useState<'24h' | '7d' | '30d' | 'all'>('all');
  const ws = useWebSocket();

  useEffect(() => {
    if (!ws) return;

    const handlePositionClosed = (payload: unknown) => {
      const data = payload as PositionClosedPayload;
      const trade: TradeRecord = {
        id: data.position_id,
        positionId: data.position_id,
        symbol: data.symbol || 'TOKEN',
        entryPrice: data.entry_price_sol || 0,
        exitPrice: data.exit_price || 0,
        quantity: data.quantity || 0,
        pnl: data.realised_pnl_sol || 0,
        pnlPct: 0,
        exitReason: (data.exit_reason as 'tp1' | 'tp2' | 'sl' | 'manual' | 'time') || 'manual',
        entryTime: new Date(Date.now() - Math.random() * 86400000).toISOString(),
        exitTime: new Date().toISOString(),
        fees: 0.001,
      };
      trade.pnlPct = trade.entryPrice > 0 ? ((trade.exitPrice - trade.entryPrice) / trade.entryPrice) * 100 : 0;
      
      setTrades(prev => {
        const filtered = prev.filter(t => t.positionId !== data.position_id);
        return [...filtered, trade];
      });
    };

    ws.subscribe('position_closed', handlePositionClosed);

    return () => {
      ws.unsubscribe('position_closed', handlePositionClosed);
    };
  }, [ws]);

  useEffect(() => {
    localStorage.setItem('mtus_trade_history', JSON.stringify(trades));
  }, [trades]);

  const filteredTrades = useMemo(() => {
    let result = trades;
    
    if (filter === 'win') result = result.filter(t => t.pnl > 0);
    if (filter === 'loss') result = result.filter(t => t.pnl < 0);
    
    if (dateRange !== 'all') {
      const ranges: Record<string, number> = {
        '24h': 86400000,
        '7d': 604800000,
        '30d': 2592000000,
      };
      const cutoff = ranges[dateRange];
      result = result.filter(t => {
        const exitTime = new Date(t.exitTime).getTime();
        const now = Date.now();
        return exitTime > now - cutoff;
      });
    }
    
    return result.sort((a, b) => new Date(b.exitTime).getTime() - new Date(a.exitTime).getTime());
  }, [trades, filter, dateRange]);

  const stats = useMemo(() => {
    const wins = filteredTrades.filter(t => t.pnl > 0).length;
    const losses = filteredTrades.filter(t => t.pnl < 0).length;
    const totalPnl = filteredTrades.reduce((sum, t) => sum + t.pnl, 0);
    const winRate = (wins / (wins + losses)) * 100 || 0;
    
    return { wins, losses, totalPnl, winRate, total: filteredTrades.length };
  }, [filteredTrades]);

  const exportToCSV = () => {
    const headers = ['ID', 'Symbol', 'Entry Price', 'Exit Price', 'Quantity', 'PnL', 'PnL %', 'Exit Reason', 'Entry Time', 'Exit Time', 'Fees'];
    const rows = filteredTrades.map(t => [
      t.positionId,
      t.symbol,
      t.entryPrice.toFixed(6),
      t.exitPrice.toFixed(6),
      t.quantity.toString(),
      t.pnl.toFixed(6),
      t.pnlPct.toFixed(2),
      t.exitReason,
      t.entryTime,
      t.exitTime,
      t.fees.toString()
    ]);
    
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mtus_trades_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Trade History</h1>
        <button 
          onClick={exportToCSV}
          className="flex items-center gap-2 px-4 py-2 bg-mtus-accent text-white rounded-lg hover:bg-opacity-90"
        >
          <Download size={16} />
          Export CSV
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <DollarSign size={16} />
            <span className="text-sm">Total PnL</span>
          </div>
          <p className={`text-2xl font-bold ${stats.totalPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
            {stats.totalPnl >= 0 ? '+' : ''}{stats.totalPnl.toFixed(4)} SOL
          </p>
        </div>
        
        <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <TrendingUp size={16} />
            <span className="text-sm">Win Rate</span>
          </div>
          <p className="text-2xl font-bold text-white">{stats.winRate.toFixed(1)}%</p>
        </div>
        
        <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <TrendingUp size={16} />
            <span className="text-sm">Wins</span>
          </div>
          <p className="text-2xl font-bold text-profit">{stats.wins}</p>
        </div>
        
        <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <TrendingDown size={16} />
            <span className="text-sm">Losses</span>
          </div>
          <p className="text-2xl font-bold text-loss">{stats.losses}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Filter size={16} className="text-slate-400" />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as 'all' | 'win' | 'loss')}
            className="bg-mtus-card text-white border border-slate-700 rounded-lg px-3 py-2"
          >
            <option value="all">All Trades</option>
            <option value="win">Wins Only</option>
            <option value="loss">Losses Only</option>
          </select>
        </div>
        
        <select
          value={dateRange}
          onChange={(e) => setDateRange(e.target.value as '24h' | '7d' | '30d' | 'all')}
          className="bg-mtus-card text-white border border-slate-700 rounded-lg px-3 py-2"
        >
          <option value="24h">Last 24 Hours</option>
          <option value="7d">Last 7 Days</option>
          <option value="30d">Last 30 Days</option>
          <option value="all">All Time</option>
        </select>
      </div>

      {/* Trade Table */}
      {filteredTrades.length > 0 ? (
        <div className="bg-mtus-card rounded-xl border border-slate-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-800">
                <tr>
                  <th className="px-4 py-3 text-left text-sm text-slate-400">Symbol</th>
                  <th className="px-4 py-3 text-right text-sm text-slate-400">Entry</th>
                  <th className="px-4 py-3 text-right text-sm text-slate-400">Exit</th>
                  <th className="px-4 py-3 text-right text-sm text-slate-400">PnL</th>
                  <th className="px-4 py-3 text-right text-sm text-slate-400">Reason</th>
                  <th className="px-4 py-3 text-right text-sm text-slate-400">Time</th>
                </tr>
              </thead>
              <tbody>
                {filteredTrades.map((trade, idx) => (
                  <tr key={idx} className="border-t border-slate-700 hover:bg-slate-800/50">
                    <td className="px-4 py-3">
                      <span className="font-medium text-white">{trade.symbol}</span>
                    </td>
                    <td className="px-4 py-3 text-right text-slate-400">
                      ${trade.entryPrice.toFixed(6)}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-400">
                      ${trade.exitPrice.toFixed(6)}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${trade.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(4)} SOL
                      <span className="text-xs ml-1">({trade.pnlPct.toFixed(1)}%)</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`px-2 py-1 rounded text-xs ${
                        trade.exitReason === 'tp1' || trade.exitReason === 'tp2' ? 'bg-profit/20 text-profit' :
                        trade.exitReason === 'sl' ? 'bg-loss/20 text-loss' :
                        'bg-slate-700 text-slate-400'
                      }`}>
                        {trade.exitReason.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-slate-400 text-sm">
                      {new Date(trade.exitTime).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-center py-16 text-slate-500 bg-mtus-card rounded-xl border border-slate-700">
          <Clock size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-lg">No trades yet</p>
          <p className="text-sm mt-2">Closed positions will appear here</p>
        </div>
      )}
    </div>
  );
}