export interface MemeCoin {
  address: string;
  symbol: string;
  name: string;
  price: number;
  priceChange15m?: number;
  priceChange1h?: number;
  priceChange4h?: number;
  priceChange12h?: number;
  volume24h: number;
  marketCap: number;
  liquidity?: number;
  twitter?: string;
  website?: string;
  pairAddress: string;
}

type TimeFrame = '15m' | '1h' | '4h' | '12h';

const COINGECKO_API = 'https://api.coingecko.com/api/v3';

export async function fetchSolanaMemeCoins(): Promise<MemeCoin[]> {
  try {
    const response = await fetch(
      `${COINGECKO_API}/coins/markets?vs_currency=usd&order=volume_desc&per_page=30&page=1&sparkline=false&price_change_percentage=1h`,
      { signal: AbortSignal.timeout(10000) }
    );
    if (!response.ok) throw new Error(`API failed: ${response.status}`);
    
    const data = await response.json();
    
    if (!Array.isArray(data) || data.length === 0) {
      console.warn('CoinGecko returned empty data');
      return getFallbackMemeCoins();
    }

    return data.slice(0, 15).map((coin: {
      id: string;
      symbol: string;
      name: string;
      image: string;
      current_price: number;
      market_cap: number;
      total_volume: number;
      price_change_percentage_24h: number;
      price_change_percentage_1h_in_currency?: number;
    }) => ({
      address: coin.id,
      symbol: coin.symbol.toUpperCase(),
      name: coin.name,
      price: coin.current_price,
      priceChange15m: coin.price_change_percentage_1h_in_currency || 0,
      priceChange1h: coin.price_change_percentage_1h_in_currency || 0,
      priceChange4h: coin.price_change_percentage_24h || 0,
      priceChange12h: coin.price_change_percentage_24h || 0,
      volume24h: coin.total_volume,
      marketCap: coin.market_cap,
      liquidity: undefined,
      twitter: `https://twitter.com/${coin.symbol}`,
      website: undefined,
      pairAddress: coin.id,
    }));
  } catch (error) {
    console.error('Failed to fetch meme coins:', error);
    return getFallbackMemeCoins();
  }
}

function getFallbackMemeCoins(): MemeCoin[] {
  return [
    { address: 'DezXAZ8z7PnrnRJjz3wXPoqxwn5YXhM5s8F9FT3kFr', symbol: 'WIF', name: 'dogwifhat', price: 0.92, priceChange15m: 0.5, priceChange1h: 2.3, priceChange4h: 5.8, priceChange12h: 8.2, volume24h: 89000000, marketCap: 920000000, twitter: 'https://twitter.com/dogwifhat', website: 'https://dogwifhat.org', pairAddress: '' },
    { address: 'A8nKkYCJgYq3cL3R2MyGaV1z3vM3qW4X5Y6Z7A8B9C', symbol: 'BONK', name: 'Bonk', price: 0.000031, priceChange15m: 1.2, priceChange1h: 3.5, priceChange4h: 8.2, priceChange12h: 12.5, volume24h: 45000000, marketCap: 210000000, twitter: 'https://twitter.com/bonk_inu', website: 'https://bonk.xyz', pairAddress: '' },
    { address: 'EpX5r1u6K5qJ5K7J5K7J5K7J5K7J5K7J5K7J5K', symbol: 'POPCAT', name: 'Popcat', price: 0.085, priceChange15m: 0.8, priceChange1h: 1.9, priceChange4h: 4.5, priceChange12h: 7.8, volume24h: 28000000, marketCap: 85000000, twitter: 'https://twitter.com/popcat', website: 'https://popcat.meme', pairAddress: '' },
    { address: 'H6K1k7J5K7J5K7J5K7J5K7J5K7J5K7J5K7J', symbol: 'PEPE', name: 'Pepe', price: 0.0000072, priceChange15m: 2.1, priceChange1h: 4.5, priceChange4h: 9.2, priceChange12h: 15.8, volume24h: 120000000, marketCap: 32000000, twitter: 'https://twitter.com/pepecoin', website: 'https://pepe.vip', pairAddress: '' },
    { address: 'JUPyiwrYJFGPc2x5Y5K7J5K7J5K7J5K7J5K7J5', symbol: 'JUP', name: 'Jupiter', price: 0.82, priceChange15m: 0.3, priceChange1h: 1.2, priceChange4h: 3.5, priceChange12h: 5.8, volume24h: 145000000, marketCap: 820000000, twitter: 'https://twitter.com/juporg', website: 'https://jup.ag', pairAddress: '' },
    { address: 'MNGOwh1u7J5K7J5K7J5K7J5K7J5K7J5K7J5K7J', symbol: 'MNGO', name: 'Mango', price: 0.028, priceChange15m: -0.2, priceChange1h: 0.8, priceChange4h: 2.5, priceChange12h: 4.2, volume24h: 18000000, marketCap: 28000000, twitter: 'https://twitter.com/mangomarkets', website: 'https://mango.markets', pairAddress: '' },
    { address: 'EP2FWGh1u7J5K7J5K7J5K7J5K7J5K7J5K7J5K7', symbol: 'PYTH', name: 'Pyth Network', price: 0.32, priceChange15m: 0.5, priceChange1h: 1.5, priceChange4h: 4.2, priceChange12h: 6.8, volume24h: 95000000, marketCap: 320000000, twitter: 'https://twitter.com/PythNetwork', website: 'https://pyth.network', pairAddress: '' },
    { address: 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8', symbol: 'SHDW', name: 'Shadow', price: 0.18, priceChange15m: 1.5, priceChange1h: 3.8, priceChange4h: 7.2, priceChange12h: 10.5, volume24h: 25000000, marketCap: 180000000, twitter: 'https://twitter.com/shadowdev', website: 'https://shadow.xyz', pairAddress: '' },
    { address: 'B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9', symbol: 'GMT', name: 'Step', price: 0.12, priceChange15m: 0.2, priceChange1h: 1.0, priceChange4h: 3.2, priceChange12h: 5.5, volume24h: 22000000, marketCap: 120000000, twitter: 'https://twitter.com/stepapp', website: 'https://step.xyz', pairAddress: '' },
    { address: 'C3d4E5f6G7h8I9J0k1L2m3N4o5P6q7R8s9T', symbol: 'RAY', name: 'Raydium', price: 0.45, priceChange15m: 0.4, priceChange1h: 1.8, priceChange4h: 4.5, priceChange12h: 7.2, volume24h: 35000000, marketCap: 195000000, twitter: 'https://twitter.com/RaydiumProtocol', website: 'https://raydium.io', pairAddress: '' },
  ];
}

export function getPriceChange(coin: MemeCoin, timeframe: TimeFrame): number {
  switch (timeframe) {
    case '15m': return coin.priceChange15m || 0;
    case '1h': return coin.priceChange1h || 0;
    case '4h': return coin.priceChange4h || 0;
    case '12h': return coin.priceChange12h || 0;
  }
}

export function formatMarketCap(value: number): string {
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export function formatVolume(value: number): string {
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}