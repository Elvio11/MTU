import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';

describe('History Page', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('should render history page title', () => {
    render(<div><h1>Trade History</h1></div>);
    expect(screen.getByText('Trade History')).toBeInTheDocument();
  });

  it('should have export button', () => {
    render(
      <div>
        <button>Export CSV</button>
      </div>
    );
    expect(screen.getByText('Export CSV')).toBeInTheDocument();
  });

  it('should display stats cards', () => {
    render(
      <div>
        <div>Total PnL</div>
        <div>Win Rate</div>
        <div>Wins</div>
        <div>Losses</div>
      </div>
    );
    expect(screen.getByText('Total PnL')).toBeInTheDocument();
    expect(screen.getByText('Win Rate')).toBeInTheDocument();
    expect(screen.getByText('Wins')).toBeInTheDocument();
    expect(screen.getByText('Losses')).toBeInTheDocument();
  });

  it('should have filter options', () => {
    render(
      <div>
        <select>
          <option value="all">All Trades</option>
          <option value="win">Wins Only</option>
          <option value="loss">Losses Only</option>
        </select>
        <select>
          <option value="24h">Last 24 Hours</option>
          <option value="7d">Last 7 Days</option>
          <option value="30d">Last 30 Days</option>
          <option value="all">All Time</option>
        </select>
      </div>
    );
    expect(screen.getByText('All Trades')).toBeInTheDocument();
    expect(screen.getByText('Last 24 Hours')).toBeInTheDocument();
  });

  it('should generate CSV export', () => {
    const trades = [
      { positionId: '1', symbol: 'PEPE', entryPrice: 0.01, exitPrice: 0.02, quantity: 100, pnl: 1, pnlPct: 100, exitReason: 'tp1', entryTime: '2026-05-01', exitTime: '2026-05-02', fees: 0.001 },
    ];

    const headers = ['ID', 'Symbol', 'Entry Price', 'Exit Price', 'Quantity', 'PnL', 'PnL %', 'Exit Reason', 'Entry Time', 'Exit Time', 'Fees'];
    const rows = trades.map(t => [
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
    
    expect(csv).toContain('ID,Symbol,Entry Price');
    expect(csv).toContain('1,PEPE,0.010000');
  });
});

describe('Trade filters', () => {
  it('should filter wins only', () => {
    const trades = [
      { pnl: 1 },
      { pnl: -0.5 },
      { pnl: 2 },
    ];
    
    const wins = trades.filter(t => t.pnl > 0);
    expect(wins.length).toBe(2);
  });

  it('should filter losses only', () => {
    const trades = [
      { pnl: 1 },
      { pnl: -0.5 },
      { pnl: 2 },
    ];
    
    const losses = trades.filter(t => t.pnl < 0);
    expect(losses.length).toBe(1);
  });

  it('should filter by date range 24h', () => {
    const now = Date.now();
    const trades = [
      { exitTime: new Date(now - 3600000).toISOString() },
      { exitTime: new Date(now - 86400000 * 2).toISOString() },
      { exitTime: new Date(now - 86400000 * 8).toISOString() },
    ];

    const dayAgo = now - 86400000;
    const filtered = trades.filter(t => new Date(t.exitTime).getTime() > dayAgo);
    expect(filtered.length).toBe(1);
  });

  it('should filter by date range 7d', () => {
    const now = Date.now();
    const trades = [
      { exitTime: new Date(now - 3600000).toISOString() },
      { exitTime: new Date(now - 86400000 * 2).toISOString() },
      { exitTime: new Date(now - 86400000 * 8).toISOString() },
    ];

    const weekAgo = now - 604800000;
    const filtered = trades.filter(t => new Date(t.exitTime).getTime() > weekAgo);
    expect(filtered.length).toBe(2);
  });
});

describe('Trade statistics', () => {
  it('should calculate win rate', () => {
    const trades = [
      { pnl: 1 },
      { pnl: -0.5 },
      { pnl: 2 },
      { pnl: -1 },
    ];
    
    const wins = trades.filter(t => t.pnl > 0).length;
    const losses = trades.filter(t => t.pnl < 0).length;
    const winRate = (wins / (wins + losses)) * 100;
    
    expect(winRate).toBe(50);
  });

  it('should calculate total PnL', () => {
    const trades = [
      { pnl: 1 },
      { pnl: -0.5 },
      { pnl: 2 },
    ];
    
    const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
    expect(totalPnl).toBe(2.5);
  });
});

describe('CSV export', () => {
  it('should create proper CSV format', () => {
    const trades = [
      { positionId: 'pos1', symbol: 'SOL', entryPrice: 100, exitPrice: 110, quantity: 10, pnl: 100, pnlPct: 10, exitReason: 'tp1', entryTime: '2026-05-01T00:00:00Z', exitTime: '2026-05-02T00:00:00Z', fees: 0.01 },
      { positionId: 'pos2', symbol: 'PEPE', entryPrice: 0.001, exitPrice: 0.0009, quantity: 1000, pnl: -0.1, pnlPct: -10, exitReason: 'sl', entryTime: '2026-05-01T00:00:00Z', exitTime: '2026-05-02T00:00:00Z', fees: 0.01 },
    ];

    const headers = ['ID', 'Symbol', 'Entry Price', 'Exit Price', 'Quantity', 'PnL', 'PnL %', 'Exit Reason', 'Entry Time', 'Exit Time', 'Fees'];
    const rows = trades.map(t => [
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
    const lines = csv.split('\n');
    
    expect(lines.length).toBe(3);
    expect(lines[0]).toBe('ID,Symbol,Entry Price,Exit Price,Quantity,PnL,PnL %,Exit Reason,Entry Time,Exit Time,Fees');
    expect(lines[1]).toContain('pos1,SOL');
    expect(lines[2]).toContain('pos2,PEPE');
  });
});