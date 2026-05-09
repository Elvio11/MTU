import { useWebSocket } from '@/lib/websocket';

interface PositionCardProps {
  position: {
    positionId: string;
    mint: string;
    symbol?: string;
    entryPrice: number;
    currentPrice: number;
    pnl: number;
    pnlPct: number;
    state: string;
    quantity?: number;
  };
}

export default function PositionCard({ position }: PositionCardProps) {
  const ws = useWebSocket();
  const isPositive = position.pnl >= 0;

  const stateColors: Record<string, string> = {
    'OPEN': 'bg-mtus-accent',
    'TP1_HIT': 'bg-profit',
    'TP2_HIT': 'bg-profit',
    'STOP_LOSS': 'bg-loss',
    'CLOSED': 'bg-muted',
    'LIQUIDATED': 'bg-loss',
  };

  const handleClose = () => {
    if (confirm(`Close position ${position.positionId}?`)) {
      ws?.send({ type: 'close_position', positionId: position.positionId });
    }
  };

  return (
    <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-semibold text-white">{position.symbol || 'TOKEN'}</h3>
          <p className="text-xs text-slate-400">{position.mint.slice(0, 8)}...</p>
        </div>
        <span className={`px-2 py-1 rounded text-xs text-white ${stateColors[position.state] || 'bg-muted'}`}>
          {position.state}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm mb-3">
        <div>
          <p className="text-slate-400 text-xs">Entry Price</p>
          <p className="text-white font-medium">{position.entryPrice.toFixed(6)} SOL</p>
        </div>
        <div>
          <p className="text-slate-400 text-xs">Current</p>
          <p className="text-white font-medium">{position.currentPrice.toFixed(6)} SOL</p>
        </div>
        {position.quantity !== undefined && (
          <div>
            <p className="text-slate-400 text-xs">Quantity</p>
            <p className="text-white font-medium">{position.quantity.toFixed(4)}</p>
          </div>
        )}
      </div>

      <div className="border-t border-slate-700 pt-3">
        <div className="flex justify-between items-center">
          <div>
            <p className={`text-lg font-bold ${isPositive ? 'text-profit' : 'text-loss'}`}>
              {isPositive ? '+' : ''}{position.pnl.toFixed(4)} SOL
            </p>
            <p className={`text-sm ${isPositive ? 'text-profit' : 'text-loss'}`}>
              ({isPositive ? '+' : ''}{position.pnlPct.toFixed(1)}%)
            </p>
          </div>
          {position.state === 'OPEN' && (
            <button
              onClick={handleClose}
              className="px-3 py-1.5 bg-loss hover:bg-red-700 rounded text-sm font-medium transition-colors disabled:opacity-50"
              disabled={!ws?.connected}
            >
              Close
            </button>
          )}
        </div>
      </div>
    </div>
  );
}