import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchSolanaMemeCoins,
  getPriceChange,
  formatMarketCap,
  formatVolume,
  type MemeCoin,
} from './meme-coins';

const mockCoin: MemeCoin = {
  address: 'test-address',
  symbol: 'TEST',
  name: 'Test Coin',
  price: 1.23,
  priceChange15m: 0.5,
  priceChange1h: 2.3,
  priceChange4h: 5.8,
  priceChange12h: 8.2,
  volume24h: 1000000,
  marketCap: 50000000,
  liquidity: undefined,
  twitter: 'https://twitter.com/test',
  website: undefined,
  pairAddress: 'test-address',
};

const mockApiResponse = [
  {
    id: 'bitcoin',
    symbol: 'btc',
    name: 'Bitcoin',
    image: 'https://example.com/btc.png',
    current_price: 50000,
    market_cap: 1000000000000,
    total_volume: 50000000000,
    price_change_percentage_24h: 2.5,
    price_change_percentage_1h_in_currency: 0.5,
  },
];

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('fetchSolanaMemeCoins', () => {
  it('returns mapped coins on successful API call', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockApiResponse),
    } as Response);

    const coins = await fetchSolanaMemeCoins();

    expect(coins).toHaveLength(1);
    expect(coins[0].address).toBe('bitcoin');
    expect(coins[0].symbol).toBe('BTC');
    expect(coins[0].name).toBe('Bitcoin');
    expect(coins[0].price).toBe(50000);
    expect(coins[0].priceChange15m).toBe(0.5);
    expect(coins[0].priceChange1h).toBe(0.5);
    expect(coins[0].priceChange4h).toBe(2.5);
    expect(coins[0].priceChange12h).toBe(2.5);
    expect(coins[0].volume24h).toBe(50000000000);
    expect(coins[0].marketCap).toBe(1000000000000);
    expect(coins[0].twitter).toBe('https://twitter.com/btc');
    expect(coins[0].pairAddress).toBe('bitcoin');
  });

  it('limits results to 15 coins', async () => {
    const manyCoins = Array.from({ length: 30 }, (_, i) => ({
      id: `coin-${i}`,
      symbol: `c${i}`,
      name: `Coin ${i}`,
      image: '',
      current_price: 1,
      market_cap: 1000,
      total_volume: 100,
      price_change_percentage_24h: 0,
    }));

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(manyCoins),
    } as Response);

    const coins = await fetchSolanaMemeCoins();

    expect(coins).toHaveLength(15);
  });

  it('returns fallback data when API response is empty array', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([]),
    } as Response);

    const coins = await fetchSolanaMemeCoins();

    expect(coins).toHaveLength(10);
    expect(coins[0].symbol).toBe('WIF');
    expect(coins[1].symbol).toBe('BONK');
    expect(console.warn).toHaveBeenCalledWith('CoinGecko returned empty data');
  });

  it('returns fallback data when API response is not an array', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ error: 'bad request' }),
    } as Response);

    const coins = await fetchSolanaMemeCoins();

    expect(coins).toHaveLength(10);
  });

  it('returns fallback data on fetch failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

    const coins = await fetchSolanaMemeCoins();

    expect(coins).toHaveLength(10);
    expect(coins[0].symbol).toBe('WIF');
    expect(console.error).toHaveBeenCalled();
  });

  it('returns fallback data on non-ok response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 429,
    } as Response);

    const coins = await fetchSolanaMemeCoins();

    expect(coins).toHaveLength(10);
    expect(console.error).toHaveBeenCalled();
  });
});

describe('getPriceChange', () => {
  const coin: MemeCoin = {
    address: 'addr',
    symbol: 'TEST',
    name: 'Test',
    price: 1,
    priceChange15m: 1.5,
    priceChange1h: 2.5,
    priceChange4h: 3.5,
    priceChange12h: 4.5,
    volume24h: 1000,
    marketCap: 5000,
    pairAddress: 'addr',
  };

  it('returns priceChange15m for "15m" timeframe', () => {
    expect(getPriceChange(coin, '15m')).toBe(1.5);
  });

  it('returns priceChange1h for "1h" timeframe', () => {
    expect(getPriceChange(coin, '1h')).toBe(2.5);
  });

  it('returns priceChange4h for "4h" timeframe', () => {
    expect(getPriceChange(coin, '4h')).toBe(3.5);
  });

  it('returns priceChange12h for "12h" timeframe', () => {
    expect(getPriceChange(coin, '12h')).toBe(4.5);
  });

  it('returns 0 when the price change field is undefined', () => {
    const partial: MemeCoin = { ...coin, priceChange15m: undefined };
    expect(getPriceChange(partial, '15m')).toBe(0);
  });
});

describe('formatMarketCap', () => {
  it('formats billions with B suffix', () => {
    expect(formatMarketCap(1_500_000_000)).toBe('$1.50B');
    expect(formatMarketCap(10_000_000_000)).toBe('$10.00B');
  });

  it('formats millions with M suffix', () => {
    expect(formatMarketCap(5_000_000)).toBe('$5.00M');
    expect(formatMarketCap(123_000_000)).toBe('$123.00M');
  });

  it('formats thousands with K suffix', () => {
    expect(formatMarketCap(500_000)).toBe('$500K');
    expect(formatMarketCap(999_000)).toBe('$999K');
  });

  it('formats values below 1000 without suffix', () => {
    expect(formatMarketCap(500)).toBe('$500');
    expect(formatMarketCap(0)).toBe('$0');
    expect(formatMarketCap(999)).toBe('$999');
  });
});

describe('formatVolume', () => {
  it('formats millions with M suffix (one decimal)', () => {
    expect(formatVolume(5_000_000)).toBe('$5.0M');
    expect(formatVolume(12_500_000)).toBe('$12.5M');
  });

  it('formats thousands with K suffix', () => {
    expect(formatVolume(500_000)).toBe('$500K');
    expect(formatVolume(999_000)).toBe('$999K');
  });

  it('formats values below 1000 without suffix', () => {
    expect(formatVolume(500)).toBe('$500');
    expect(formatVolume(0)).toBe('$0');
    expect(formatVolume(999)).toBe('$999');
  });
});
