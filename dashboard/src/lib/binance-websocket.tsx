"use client";

import React, { createContext, useContext, useEffect, useState, useRef, ReactNode } from 'react';

export interface BinanceTicker {
  symbol: string;
  price: number;
  change24h: number;
  changePercent24h: number;
  high24h: number;
  low24h: number;
  volume24h: number;
  lastUpdate: number;
}

export interface BinanceContextType {
  tickers: Map<string, BinanceTicker>;
  connected: boolean;
  refreshStats: () => Promise<void>;
}

const BinanceContext = createContext<BinanceContextType>({
  tickers: new Map(),
  connected: false,
  refreshStats: async () => {},
});

const BINANCE_WS_URL = 'wss://stream.binance.com:9443/ws';
const BINANCE_API_URL = 'https://api.binance.com/api/v3';
const SYMBOLS = [
  'btcusdt', 'ethusdt', 'solusdt', 'bnbusdt', 'xrpusdt', 'dogeusdt', 'adausdt', 'dotusdt', 'maticusdt', 'ltcusdt',
  'avaxusdt', 'linkusdt', 'uniusdt', 'atomusdt', 'leousdt', 'xlmusdt', 'aptusdt', 'arbusdt', 'neousdt', 'opousdt',
  'injusdt', 'renderusdt', 'filusdt', 'nearusdt', 'algousdt', 'ftmusdt'
];
const UPDATE_INTERVAL = 1000;

const FALLBACK_TICKERS: BinanceTicker[] = [
  { symbol: 'BTC', price: 80123.17, change24h: 1523.45, changePercent24h: 1.94, high24h: 81200, low24h: 78500, volume24h: 28500000000, lastUpdate: Date.now() },
  { symbol: 'ETH', price: 2356.48, change24h: 45.32, changePercent24h: 1.96, high24h: 2380, low24h: 2290, volume24h: 12500000000, lastUpdate: Date.now() },
  { symbol: 'SOL', price: 84.34, change24h: 3.21, changePercent24h: 3.96, high24h: 86.5, low24h: 80.1, volume24h: 1850000000, lastUpdate: Date.now() },
  { symbol: 'BNB', price: 625.37, change24h: -8.45, changePercent24h: -1.33, high24h: 638, low24h: 618, volume24h: 890000000, lastUpdate: Date.now() },
  { symbol: 'XRP', price: 1.40, change24h: 0.12, changePercent24h: 9.37, high24h: 1.52, low24h: 1.28, volume24h: 4500000000, lastUpdate: Date.now() },
  { symbol: 'DOGE', price: 0.11, change24h: 0.008, changePercent24h: 7.84, high24h: 0.115, low24h: 0.098, volume24h: 1850000000, lastUpdate: Date.now() },
  { symbol: 'ADA', price: 0.25, change24h: 0.015, changePercent24h: 6.38, high24h: 0.262, low24h: 0.232, volume24h: 520000000, lastUpdate: Date.now() },
  { symbol: 'DOT', price: 1.23, change24h: 0.045, changePercent24h: 3.80, high24h: 1.28, low24h: 1.18, volume24h: 180000000, lastUpdate: Date.now() },
  { symbol: 'MATIC', price: 0.38, change24h: 0.022, changePercent24h: 6.15, high24h: 0.395, low24h: 0.355, volume24h: 145000000, lastUpdate: Date.now() },
  { symbol: 'LTC', price: 55.27, change24h: 1.85, changePercent24h: 3.46, high24h: 56.8, low24h: 52.5, volume24h: 320000000, lastUpdate: Date.now() },
  { symbol: 'AVAX', price: 22.45, change24h: 1.20, changePercent24h: 5.65, high24h: 23.5, low24h: 21.2, volume24h: 280000000, lastUpdate: Date.now() },
  { symbol: 'LINK', price: 14.82, change24h: 0.35, changePercent24h: 2.42, high24h: 15.2, low24h: 14.1, volume24h: 195000000, lastUpdate: Date.now() },
  { symbol: 'UNI', price: 7.25, change24h: 0.18, changePercent24h: 2.55, high24h: 7.5, low24h: 6.9, volume24h: 145000000, lastUpdate: Date.now() },
  { symbol: 'ATOM', price: 6.12, change24h: 0.25, changePercent24h: 4.26, high24h: 6.4, low24h: 5.8, volume24h: 165000000, lastUpdate: Date.now() },
  { symbol: 'LEO', price: 5.85, change24h: -0.05, changePercent24h: -0.85, high24h: 6.1, low24h: 5.6, volume24h: 28000000, lastUpdate: Date.now() },
  { symbol: 'XLM', price: 0.092, change24h: 0.005, changePercent24h: 5.75, high24h: 0.098, low24h: 0.085, volume24h: 185000000, lastUpdate: Date.now() },
  { symbol: 'APT', price: 8.45, change24h: 0.32, changePercent24h: 3.94, high24h: 8.8, low24h: 8.0, volume24h: 245000000, lastUpdate: Date.now() },
  { symbol: 'ARB', price: 0.78, change24h: 0.04, changePercent24h: 5.41, high24h: 0.82, low24h: 0.72, volume24h: 195000000, lastUpdate: Date.now() },
  { symbol: 'NEO', price: 12.35, change24h: 0.45, changePercent24h: 3.78, high24h: 12.8, low24h: 11.6, volume24h: 85000000, lastUpdate: Date.now() },
  { symbol: 'OP', price: 1.52, change24h: 0.08, changePercent24h: 5.56, high24h: 1.6, low24h: 1.4, volume24h: 125000000, lastUpdate: Date.now() },
  { symbol: 'INJ', price: 18.45, change24h: 0.85, changePercent24h: 4.83, high24h: 19.2, low24h: 17.5, volume24h: 145000000, lastUpdate: Date.now() },
  { symbol: 'RENDER', price: 2.85, change24h: 0.15, changePercent24h: 5.56, high24h: 3.0, low24h: 2.6, volume24h: 185000000, lastUpdate: Date.now() },
  { symbol: 'FIL', price: 3.92, change24h: 0.12, changePercent24h: 3.16, high24h: 4.1, low24h: 3.7, volume24h: 165000000, lastUpdate: Date.now() },
  { symbol: 'NEAR', price: 3.45, change24h: 0.18, changePercent24h: 5.50, high24h: 3.6, low24h: 3.2, volume24h: 195000000, lastUpdate: Date.now() },
  { symbol: 'ALGO', price: 0.18, change24h: 0.008, changePercent24h: 4.65, high24h: 0.19, low24h: 0.17, volume24h: 85000000, lastUpdate: Date.now() },
  { symbol: 'FTM', price: 0.42, change24h: 0.025, changePercent24h: 6.33, high24h: 0.45, low24h: 0.38, volume24h: 145000000, lastUpdate: Date.now() },
];

async function fetch24hStats(): Promise<Map<string, BinanceTicker>> {
  const tickers = new Map<string, BinanceTicker>();
  
  try {
    const response = await fetch(`${BINANCE_API_URL}/ticker/24hr`, {
      signal: AbortSignal.timeout(5000),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const data = await response.json();
    
    if (!Array.isArray(data)) {
      throw new Error('Invalid response format');
    }
    
    for (const symbol of SYMBOLS) {
      const upperSymbol = symbol.replace('usdt', '').toUpperCase();
      const tickerData = data.find((t: { symbol: string }) => t.symbol === symbol.toUpperCase());
      
      if (tickerData) {
        tickers.set(upperSymbol, {
          symbol: upperSymbol,
          price: parseFloat(tickerData.lastPrice),
          change24h: parseFloat(tickerData.priceChange),
          changePercent24h: parseFloat(tickerData.priceChangePercent),
          high24h: parseFloat(tickerData.highPrice),
          low24h: parseFloat(tickerData.lowPrice),
          volume24h: parseFloat(tickerData.volume),
          lastUpdate: Date.now(),
        });
      }
    }
  } catch (error) {
    console.warn('Binance API failed, using fallback data:', error);
    FALLBACK_TICKERS.forEach(ticker => {
      tickers.set(ticker.symbol, ticker);
    });
  }
  
  return tickers;
}

export function BinanceProvider({ children }: { children: ReactNode }) {
  const [tickers, setTickers] = useState<Map<string, BinanceTicker>>(new Map());
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const pendingUpdates = useRef<Map<string, BinanceTicker>>(new Map());
  const lastDisplayUpdate = useRef(0);
  const statsFetched = useRef(false);

  const refreshStats = async () => {
    const stats = await fetch24hStats();
    if (stats.size > 0) {
      setTickers(prev => {
        const newMap = new Map(prev);
        stats.forEach((value, key) => {
          const existing = newMap.get(key);
          newMap.set(key, {
            ...existing,
            ...value,
            price: existing?.price || value.price,
          });
        });
        return newMap;
      });
    }
  };

  useEffect(() => {
    const init = async () => {
      if (statsFetched.current) return;
      statsFetched.current = true;
      
      const initialStats = await fetch24hStats();
      if (initialStats.size > 0) {
        setTickers(initialStats);
        pendingUpdates.current = new Map(initialStats);
      }
    };
    
    init();

    const connect = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      const streams = SYMBOLS.map(s => `${s}@trade`).join('/');
      const wsUrl = `${BINANCE_WS_URL}/${streams}`;
      
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        setConnected(true);
        reconnectAttempts.current = 0;
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.s) {
            const symbol = data.s.replace('USDT', '');
            const price = parseFloat(data.p);
            
            const existing = tickers.get(symbol) || pendingUpdates.current.get(symbol);
            
            pendingUpdates.current.set(symbol, {
              symbol,
              price,
              change24h: existing?.change24h || 0,
              changePercent24h: existing?.changePercent24h || 0,
              high24h: existing?.high24h || price,
              low24h: existing?.low24h || price,
              volume24h: existing?.volume24h || 0,
              lastUpdate: Date.now(),
            });
          }
        } catch (e) {
          console.error('Binance WS parse error:', e);
        }
      };

      wsRef.current.onclose = () => {
        setConnected(false);
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          reconnectTimer.current = setTimeout(connect, 3000);
        }
      };

      wsRef.current.onerror = () => {
        reconnectAttempts.current++;
      };
    };

    connect();

    const updateInterval = setInterval(() => {
      const now = Date.now();
      if (now - lastDisplayUpdate.current >= UPDATE_INTERVAL && pendingUpdates.current.size > 0) {
        setTickers(new Map(pendingUpdates.current));
        lastDisplayUpdate.current = now;
      }
    }, 250);

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      clearInterval(updateInterval);
      if (wsRef.current) wsRef.current.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <BinanceContext.Provider value={{ tickers, connected, refreshStats }}>
      {children}
    </BinanceContext.Provider>
  );
}

export function useBinance(): BinanceContextType {
  return useContext(BinanceContext);
}

export function useBinanceTicker(symbol: string): BinanceTicker | undefined {
  const { tickers } = useBinance();
  return tickers.get(symbol);
}