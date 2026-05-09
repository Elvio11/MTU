'use client';

import { useEffect, useState } from 'react';
import { MemeCoin, fetchSolanaMemeCoins, getPriceChange, formatMarketCap, formatVolume } from '@/lib/meme-coins';
import { RefreshCw, Twitter, ExternalLink, Flame } from 'lucide-react';

type TimeFrame = '15m' | '1h' | '4h' | '12h';

const TIME_FRAMES: { label: string; value: TimeFrame }[] = [
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '12h', value: '12h' },
];

export default function MemeCoins() {
  const [coins, setCoins] = useState<MemeCoin[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeFrame, setTimeFrame] = useState<TimeFrame>('1h');
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let mounted = true;
    
    const fetchData = () => {
      setLoading(prev => prev ? prev : true);
      fetchSolanaMemeCoins().then(data => {
        if (mounted) {
          setCoins(data);
          setLoading(false);
        }
      });
    };

    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [refreshKey]);

  return (
    <div className="bg-mtus-card rounded-xl border border-slate-700 overflow-hidden">
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <Flame className="text-warning" size={20} />
          <h3 className="font-semibold text-white">Top Trending Meme Coins on Solana</h3>
        </div>
        <button
          onClick={() => setRefreshKey(k => k + 1)}
          className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
          title="Refresh"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin text-slate-400' : 'text-slate-400'} />
        </button>
      </div>

      <div className="flex gap-2 p-3 border-b border-slate-700">
        {TIME_FRAMES.map((tf) => (
          <button
            key={tf.value}
            onClick={() => setTimeFrame(tf.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              timeFrame === tf.value
                ? 'bg-mtus-accent text-white'
                : 'bg-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            {tf.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="p-8 text-center text-slate-500">
          Loading trending coins...
        </div>
      ) : coins.length === 0 ? (
        <div className="p-8 text-center text-slate-500">
          No trending coins found
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-800/50">
              <tr className="text-left text-xs text-slate-400">
                <th className="px-4 py-3 font-medium">Token</th>
                <th className="px-4 py-3 font-medium text-right">Price</th>
                <th className="px-4 py-3 font-medium text-right">{timeFrame}</th>
                <th className="px-4 py-3 font-medium text-right">Volume (24h)</th>
                <th className="px-4 py-3 font-medium text-right">Market Cap</th>
                <th className="px-4 py-3 font-medium text-center">Links</th>
              </tr>
            </thead>
            <tbody>
              {coins.slice(0, 15).map((coin, idx) => {
                const change = getPriceChange(coin, timeFrame);
                return (
                  <tr key={coin.address} className="border-t border-slate-700/50 hover:bg-slate-800/30">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-500 text-xs">{idx + 1}</span>
                        <div>
                          <div className="font-medium text-white">{coin.symbol}</div>
                          <div className="text-xs text-slate-500">{coin.name}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-white font-mono text-sm">
                        ${coin.price < 0.01 ? coin.price.toFixed(6) : coin.price < 1 ? coin.price.toFixed(4) : coin.price.toFixed(2)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`text-sm font-medium ${change >= 0 ? 'text-profit' : 'text-loss'}`}>
                        {change >= 0 ? '+' : ''}{change.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-white text-sm">{formatVolume(coin.volume24h)}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-white text-sm">{formatMarketCap(coin.marketCap)}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-2">
                        {coin.twitter && (
                          <a
                            href={coin.twitter}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-white transition-colors"
                            title="Twitter"
                          >
                            <Twitter size={16} />
                          </a>
                        )}
                        {coin.website && (
                          <a
                            href={coin.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-white transition-colors"
                            title="Website"
                          >
                            <ExternalLink size={16} />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}