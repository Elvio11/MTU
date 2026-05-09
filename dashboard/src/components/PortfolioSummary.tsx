import { RefreshCw, Clock, Wifi, WifiOff } from 'lucide-react';

interface PortfolioSummaryProps {
  pnlTotal: number;
  totalValue: number;
  openPositions: number;
  agentsCount: number;
  connected: boolean;
  lastUpdate?: Date | null;
  onRefresh?: () => void;
  binanceConnected?: boolean;
}

export default function PortfolioSummary({ 
  pnlTotal, 
  totalValue, 
  openPositions, 
  agentsCount,
  connected,
  lastUpdate,
  onRefresh,
  binanceConnected
}: PortfolioSummaryProps) {
  return (
    <div className="bg-mtus-card rounded-xl p-6 border border-slate-700">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">MTUS Dashboard</h1>
          <div className="flex items-center gap-3 mt-1">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${connected ? 'bg-profit animate-pulse' : 'bg-loss'}`} />
              <span className="text-sm text-slate-400">
                {connected ? 'WS Connected' : 'WS Disconnected'}
              </span>
            </div>
            {binanceConnected !== undefined && (
              <div className="flex items-center gap-1 text-xs">
                {binanceConnected ? (
                  <Wifi size={12} className="text-profit" />
                ) : (
                  <WifiOff size={12} className="text-loss" />
                )}
                <span className={binanceConnected ? 'text-profit' : 'text-slate-500'}>
                  Binance {binanceConnected ? 'Live' : 'Offline'}
                </span>
              </div>
            )}
            {lastUpdate && (
              <div className="flex items-center gap-1 text-xs text-slate-500">
                <Clock size={12} />
                <span>Last update: {lastUpdate.toLocaleTimeString()}</span>
              </div>
            )}
            {onRefresh && (
              <button 
                onClick={onRefresh}
                className="text-slate-400 hover:text-white transition-colors"
                title="Refresh market data"
              >
                <RefreshCw size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-6">
          <div className="text-right">
            <p className="text-sm text-slate-400">Total PnL</p>
            <p className={`text-2xl font-bold ${pnlTotal >= 0 ? 'text-profit' : 'text-loss'}`}>
              {pnlTotal >= 0 ? '+' : ''}{pnlTotal.toFixed(4)} SOL
            </p>
          </div>

          <div className="text-right">
            <p className="text-sm text-slate-400">Portfolio Value</p>
            <p className="text-2xl font-bold text-white">${totalValue.toFixed(2)}</p>
          </div>

          <div className="text-right">
            <p className="text-sm text-slate-400">Open Positions</p>
            <p className="text-2xl font-bold text-white">{openPositions}</p>
          </div>

          <div className="text-right">
            <p className="text-sm text-slate-400">Active Agents</p>
            <p className="text-2xl font-bold text-white">{agentsCount}</p>
          </div>
        </div>
      </div>
    </div>
  );
}