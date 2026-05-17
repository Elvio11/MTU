import React from 'react';
import { GlassCard } from './GlassCard';
import { TrendingUp, Zap, BarChart3 } from 'lucide-react';

interface Position {
  positionId: string;
  mint: string;
  symbol?: string;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  pnlPct: number;
  state: string;
  quantity: number;
}

interface PositionCardProps {
  position: Position;
}

const PositionCard: React.FC<PositionCardProps> = ({ position }) => {
  const isProfit = position.pnl >= 0;

  return (
    <GlassCard 
      title={position.symbol || 'UNKNOWN'} 
      subtitle={position.mint.slice(0, 12) + '...'} 
      icon={TrendingUp}
      className="h-full"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <span className="text-[10px] font-bold text-muted uppercase tracking-widest">Entry Price</span>
            <p className="text-sm font-mono text-white/80">{position.entryPrice.toFixed(6)} SOL</p>
          </div>
          <div className="space-y-1">
            <span className="text-[10px] font-bold text-muted uppercase tracking-widest">Current Price</span>
            <p className="text-sm font-mono text-white">{position.currentPrice.toFixed(6)} SOL</p>
          </div>
        </div>

        <div className="p-3 bg-white/5 rounded-xl border border-white/5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`p-1.5 rounded-lg ${isProfit ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'}`}>
              <BarChart3 size={14} />
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-muted uppercase">Return</span>
              <span className={`text-sm font-bold ${isProfit ? 'text-profit' : 'text-loss'}`}>
                {isProfit ? '+' : ''}{position.pnlPct.toFixed(2)}%
              </span>
            </div>
          </div>
          <div className="text-right">
            <span className="text-[10px] font-bold text-muted uppercase block">PnL</span>
            <span className={`text-sm font-bold ${isProfit ? 'text-profit' : 'text-loss'}`}>
              {isProfit ? '+' : ''}{position.pnl.toFixed(4)} SOL
            </span>
          </div>
        </div>

        <div className="flex gap-2">
          <button className="flex-1 py-2 bg-mtus-accent/10 border border-mtus-accent/20 text-mtus-accent rounded-lg text-[10px] font-bold uppercase tracking-widest hover:bg-mtus-accent/20 transition-all flex items-center justify-center gap-2">
            <Zap size={12} /> Fast Sell
          </button>
          <button className="px-3 py-2 bg-white/5 border border-white/10 text-white rounded-lg text-[10px] font-bold uppercase tracking-widest hover:bg-white/10 transition-all">
            Details
          </button>
        </div>
      </div>
    </GlassCard>
  );
};

export default PositionCard;
