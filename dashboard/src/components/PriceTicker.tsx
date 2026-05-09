'use client';

import { useEffect, useState, useRef } from 'react';
import { BinanceTicker } from '@/lib/binance-websocket';

interface PriceTickerProps {
  symbol: string;
  ticker: BinanceTicker | undefined;
}

export default function PriceTicker({ symbol, ticker }: PriceTickerProps) {
  const [direction, setDirection] = useState<'up' | 'down' | null>(null);
  const [flash, setFlash] = useState(false);
  const prevPriceRef = useRef(ticker?.price ?? 0);

  useEffect(() => {
    if (ticker && ticker.price !== prevPriceRef.current) {
      const newDirection = ticker.price > prevPriceRef.current ? 'up' : 'down';
      setDirection(newDirection);
      setFlash(true);
      prevPriceRef.current = ticker.price;

      setTimeout(() => {
        setDirection(null);
        setFlash(false);
      }, 600);
    }
  }, [ticker]);

  const price = ticker?.price ?? 0;
  const changePercent = ticker?.changePercent24h ?? 0;

  return (
    <div
      className={`
        flex items-center justify-between px-3 py-2 bg-mtus-card rounded-lg border border-slate-700 
        transition-all duration-300 hover:border-slate-600
        ${flash ? (direction === 'up' ? 'border-profit shadow-[0_0_8px_rgba(34,197,94,0.2)]' : 'border-loss shadow-[0_0_8px_rgba(239,68,68,0.2)]') : ''}
      `}
    >
      <div className="flex flex-col">
        <span className="font-semibold text-white text-xs">{symbol}</span>
        <span className={`text-xs ${changePercent >= 0 ? 'text-profit' : 'text-loss'}`}>
          {changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%
        </span>
      </div>
      <span
        className={`
          text-white font-mono font-medium text-sm transition-all duration-300
          ${direction === 'up' ? 'translate-y-[-1px]' : direction === 'down' ? 'translate-y-[1px]' : ''}
        `}
      >
        ${price < 1 ? price.toFixed(4) : price.toFixed(2)}
      </span>
    </div>
  );
}