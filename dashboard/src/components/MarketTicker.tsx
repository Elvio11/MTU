import Image from 'next/image';
import { formatPrice, formatVolume } from '@/lib/market';
import { MarketCoin } from '@/lib/market';

interface MarketTickerProps {
  coin: MarketCoin;
}

export default function MarketTicker({ coin }: MarketTickerProps) {
  const isPositive = coin.price_change_percentage_24h >= 0;
  
  return (
    <div className="bg-mtus-card p-4 rounded-lg border border-slate-700 hover:border-slate-600 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <Image src={coin.image} alt={coin.name} width={20} height={20} className="w-5 h-5 rounded-full" />
        <span className="font-semibold text-white">{coin.symbol.toUpperCase()}</span>
      </div>
      <p className="text-lg font-bold text-white">{formatPrice(coin.current_price)}</p>
      <div className="flex items-center justify-between mt-2">
        <span className={`text-sm font-medium ${isPositive ? 'text-profit' : 'text-loss'}`}>
          {isPositive ? '+' : ''}{coin.price_change_percentage_24h.toFixed(2)}%
        </span>
        <span className="text-xs text-slate-400">{formatVolume(coin.total_volume)}</span>
      </div>
    </div>
  );
}