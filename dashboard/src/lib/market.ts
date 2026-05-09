export interface MarketCoin {
  id: string;
  symbol: string;
  name: string;
  image: string;
  current_price: number;
  price_change_24h: number;
  price_change_percentage_24h: number;
  market_cap: number;
  total_volume: number;
  high_24h: number;
  low_24h: number;
  sparkline_in_7d?: { price: number[] };
}

const COINGECKO_API = 'https://api.coingecko.com/api/v3';

const FALLBACK_COINS: MarketCoin[] = [
  { id: 'bitcoin', symbol: 'btc', name: 'Bitcoin', image: 'https://assets.coingecko.com/assets/images/og/large_bitcoin.png', current_price: 84520, price_change_24h: 1523, price_change_percentage_24h: 1.84, market_cap: 1680000000000, total_volume: 62000000000, high_24h: 85100, low_24h: 82100 },
  { id: 'ethereum', symbol: 'eth', name: 'Ethereum', image: 'https://assets.coingecko.com/assets/images/og/large_ethereum.png', current_price: 3280, price_change_24h: 45, price_change_percentage_24h: 1.39, market_cap: 395000000000, total_volume: 18500000000, high_24h: 3320, low_24h: 3180 },
  { id: 'solana', symbol: 'sol', name: 'Solana', image: 'https://assets.coingecko.com/assets/images/og/large_solana.png', current_price: 178.45, price_change_24h: 4.23, price_change_percentage_24h: 2.43, market_cap: 82000000000, total_volume: 3500000000, high_24h: 181, low_24h: 172 },
  { id: 'tether', symbol: 'usdt', name: 'Tether', image: 'https://assets.coingecko.com/assets/images/og/large_tether.png', current_price: 1.0, price_change_24h: 0, price_change_percentage_24h: 0.01, market_cap: 145000000000, total_volume: 65000000000, high_24h: 1.001, low_24h: 0.999 },
  { id: 'binancecoin', symbol: 'bnb', name: 'BNB', image: 'https://assets.coingecko.com/assets/images/og/large_bnb.png', current_price: 612, price_change_24h: -8, price_change_percentage_24h: -1.29, market_cap: 91000000000, total_volume: 1800000000, high_24h: 625, low_24h: 605 },
  { id: 'ripple', symbol: 'xrp', name: 'XRP', image: 'https://assets.coingecko.com/assets/images/og/large_xrp.png', current_price: 2.45, price_change_24h: 0.12, price_change_percentage_24h: 5.15, market_cap: 142000000000, total_volume: 8500000000, high_24h: 2.52, low_24h: 2.28 },
  { id: 'dogecoin', symbol: 'doge', name: 'Dogecoin', image: 'https://assets.coingecko.com/assets/images/og/large_dogecoin.png', current_price: 0.32, price_change_24h: 0.02, price_change_percentage_24h: 6.67, market_cap: 48000000000, total_volume: 3200000000, high_24h: 0.34, low_24h: 0.29 },
  { id: 'cardano', symbol: 'ada', name: 'Cardano', image: 'https://assets.coingecko.com/assets/images/og/large_cardano.png', current_price: 0.92, price_change_24h: 0.03, price_change_percentage_24h: 3.37, market_cap: 33000000000, total_volume: 890000000, high_24h: 0.95, low_24h: 0.87 },
  { id: 'sol', symbol: 'bonk', name: 'BONK', image: 'https://assets.coingecko.com/assets/images/og/large_bonk.png', current_price: 0.000031, price_change_24h: 0.000001, price_change_percentage_24h: 3.33, market_cap: 210000000, total_volume: 45000000, high_24h: 0.000033, low_24h: 0.000028 },
  { id: 'wif', symbol: 'wif', name: 'dogwifhat', image: 'https://assets.coingecko.com/assets/images/og/large_wif.png', current_price: 0.89, price_change_24h: -0.02, price_change_percentage_24h: -2.19, market_cap: 890000000, total_volume: 89000000, high_24h: 0.95, low_24h: 0.85 },
];

let cachedCoins: MarketCoin[] = [];
let lastFetch = 0;
const CACHE_DURATION = 60000;

export async function fetchTopCoins(limit: number = 20): Promise<MarketCoin[]> {
  const now = Date.now();
  
  if (cachedCoins.length > 0 && (now - lastFetch) < CACHE_DURATION) {
    return cachedCoins.slice(0, limit);
  }

  try {
    const response = await fetch(
      `${COINGECKO_API}/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=${limit}&page=1&sparkline=true&price_change_percentage=24h`,
      { 
        next: { revalidate: 60 },
        signal: AbortSignal.timeout(5000)
      }
    );
    
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }
    
    const data = await response.json();
    cachedCoins = data;
    lastFetch = now;
    return data;
  } catch (error) {
    console.warn('CoinGecko API failed, using fallback data:', error);
    if (cachedCoins.length === 0) {
      cachedCoins = FALLBACK_COINS;
    }
    return cachedCoins.slice(0, limit);
  }
}

export async function fetchCoinById(coinId: string): Promise<MarketCoin | null> {
  try {
    const response = await fetch(
      `${COINGECKO_API}/coins/${coinId}?localization=false&tickers=false&community_data=false&developer_data=false`,
      { signal: AbortSignal.timeout(5000) }
    );
    if (!response.ok) return null;
    const data = await response.json();
    return {
      id: data.id,
      symbol: data.symbol,
      name: data.name,
      image: data.image?.large || '',
      current_price: data.market_data?.current_price?.usd || 0,
      price_change_24h: data.market_data?.price_change_24h || 0,
      price_change_percentage_24h: data.market_data?.price_change_percentage_24h || 0,
      market_cap: data.market_data?.market_cap?.usd || 0,
      total_volume: data.market_data?.total_volume?.usd || 0,
      high_24h: data.market_data?.high_24h?.usd || 0,
      low_24h: data.market_data?.low_24h?.usd || 0,
    };
  } catch {
    return null;
  }
}

export function formatPrice(price: number): string {
  if (price >= 1000) return `$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (price >= 1) return `$${price.toFixed(2)}`;
  if (price >= 0.01) return `$${price.toFixed(4)}`;
  return `$${price.toFixed(6)}`;
}

export function formatVolume(volume: number): string {
  if (volume >= 1e12) return `$${(volume / 1e12).toFixed(2)}T`;
  if (volume >= 1e9) return `$${(volume / 1e9).toFixed(2)}B`;
  if (volume >= 1e6) return `$${(volume / 1e6).toFixed(2)}M`;
  return `$${(volume / 1e3).toFixed(0)}K`;
}

export function formatMarketCap(cap: number): string {
  if (cap >= 1e12) return `$${(cap / 1e12).toFixed(2)}T`;
  if (cap >= 1e9) return `$${(cap / 1e9).toFixed(2)}B`;
  if (cap >= 1e6) return `$${(cap / 1e6).toFixed(2)}M`;
  return `$${(cap / 1e3).toFixed(0)}K`;
}