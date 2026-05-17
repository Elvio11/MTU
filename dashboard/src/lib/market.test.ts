import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { formatPrice, formatVolume, formatMarketCap, fetchCoinById } from './market';

const mockCoins = [
  { id: 'bitcoin', symbol: 'btc', name: 'Bitcoin', image: 'https://example.com/btc.png', current_price: 84520, price_change_24h: 1523, price_change_percentage_24h: 1.84, market_cap: 1680000000000, total_volume: 62000000000, high_24h: 85100, low_24h: 82100 },
  { id: 'ethereum', symbol: 'eth', name: 'Ethereum', image: 'https://example.com/eth.png', current_price: 3280, price_change_24h: 45, price_change_percentage_24h: 1.39, market_cap: 395000000000, total_volume: 18500000000, high_24h: 3320, low_24h: 3180 },
  { id: 'solana', symbol: 'sol', name: 'Solana', image: 'https://example.com/sol.png', current_price: 178.45, price_change_24h: 4.23, price_change_percentage_24h: 2.43, market_cap: 82000000000, total_volume: 3500000000, high_24h: 181, low_24h: 172 },
  { id: 'tether', symbol: 'usdt', name: 'Tether', image: 'https://example.com/usdt.png', current_price: 1.0, price_change_24h: 0, price_change_percentage_24h: 0.01, market_cap: 145000000000, total_volume: 65000000000, high_24h: 1.001, low_24h: 0.999 },
  { id: 'binancecoin', symbol: 'bnb', name: 'BNB', image: 'https://example.com/bnb.png', current_price: 612, price_change_24h: -8, price_change_percentage_24h: -1.29, market_cap: 91000000000, total_volume: 1800000000, high_24h: 625, low_24h: 605 },
];

describe('formatPrice', () => {
  it('formats price >= 1000 with locale string', () => {
    expect(formatPrice(84520)).toBe('$84,520.00');
    expect(formatPrice(1000)).toBe('$1,000.00');
  });

  it('formats price >= 1 with 2 decimal places', () => {
    expect(formatPrice(3280)).toBe('$3,280.00');
    expect(formatPrice(178.45)).toBe('$178.45');
    expect(formatPrice(1)).toBe('$1.00');
  });

  it('formats price >= 0.01 with 4 decimal places', () => {
    expect(formatPrice(0.32)).toBe('$0.3200');
    expect(formatPrice(0.01)).toBe('$0.0100');
  });

  it('formats price < 0.01 with 6 decimal places', () => {
    expect(formatPrice(0.000031)).toBe('$0.000031');
    expect(formatPrice(0.000001)).toBe('$0.000001');
  });
});

describe('formatVolume', () => {
  it('formats volume >= 1e12 with T suffix', () => {
    expect(formatVolume(1680000000000)).toBe('$1.68T');
  });

  it('formats volume >= 1e9 with B suffix', () => {
    expect(formatVolume(62000000000)).toBe('$62.00B');
    expect(formatVolume(3500000000)).toBe('$3.50B');
  });

  it('formats volume >= 1e6 with M suffix', () => {
    expect(formatVolume(18500000)).toBe('$18.50M');
    expect(formatVolume(3500000)).toBe('$3.50M');
  });

  it('formats volume < 1e6 with K suffix', () => {
    expect(formatVolume(890000)).toBe('$890K');
    expect(formatVolume(45000)).toBe('$45K');
  });
});

describe('formatMarketCap', () => {
  it('formats cap >= 1e12 with T suffix', () => {
    expect(formatMarketCap(1680000000000)).toBe('$1.68T');
  });

  it('formats cap >= 1e9 with B suffix', () => {
    expect(formatMarketCap(395000000000)).toBe('$395.00B');
    expect(formatMarketCap(82000000000)).toBe('$82.00B');
  });

  it('formats cap >= 1e6 with M suffix', () => {
    expect(formatMarketCap(145000000)).toBe('$145.00M');
    expect(formatMarketCap(33000000)).toBe('$33.00M');
  });

  it('formats cap < 1e6 with K suffix', () => {
    expect(formatMarketCap(890000)).toBe('$890K');
    expect(formatMarketCap(45000)).toBe('$45K');
  });
});

describe('fetchTopCoins', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('fetches and returns coins from API', async () => {
    vi.resetModules();
    const { fetchTopCoins: fetchCoins } = await import('./market');

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCoins),
    });

    const result = await fetchCoins(5);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(result).toHaveLength(5);
    expect(result[0].id).toBe('bitcoin');
    expect(result[1].id).toBe('ethereum');
  });

  it('returns cached data on second call within cache window', async () => {
    vi.resetModules();
    const { fetchTopCoins: fetchCoins } = await import('./market');

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCoins),
    });

    await fetchCoins(5);
    const result = await fetchCoins(5);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(result).toHaveLength(5);
  });

  it('falls back to FALLBACK_COINS when API fails', async () => {
    vi.resetModules();
    const { fetchTopCoins: fetchCoins } = await import('./market');

    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const result = await fetchCoins(10);
    expect(result).toHaveLength(10);
    expect(result[0].id).toBe('bitcoin');
    expect(result[0].current_price).toBe(84520);
    expect(result[0].symbol).toBe('btc');
    expect(console.warn).toHaveBeenCalled();
  });

  it('uses fallback data when API returns non-ok response', async () => {
    vi.resetModules();
    const { fetchTopCoins: fetchCoins } = await import('./market');

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: () => Promise.resolve({}),
    });

    const result = await fetchCoins(5);
    expect(result).toHaveLength(5);
    expect(result[0].id).toBe('bitcoin');
    expect(console.warn).toHaveBeenCalled();
  });

  it('uses cached data when API fails after previous success', async () => {
    vi.resetModules();
    const { fetchTopCoins: fetchCoins } = await import('./market');

    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(mockCoins) })
      .mockRejectedValueOnce(new Error('Network error'));

    await fetchCoins(5);
    const result = await fetchCoins(5);
    expect(result).toHaveLength(5);
    expect(result[0].id).toBe('bitcoin');
  });
});

describe('fetchCoinById', () => {
  const mockDetailResponse = {
    id: 'bitcoin',
    symbol: 'btc',
    name: 'Bitcoin',
    image: { large: 'https://example.com/btc.png' },
    market_data: {
      current_price: { usd: 84520 },
      price_change_24h: 1523,
      price_change_percentage_24h: 1.84,
      market_cap: { usd: 1680000000000 },
      total_volume: { usd: 62000000000 },
      high_24h: { usd: 85100 },
      low_24h: { usd: 82100 },
    },
  };

  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches and returns a single coin', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockDetailResponse),
    });

    const result = await fetchCoinById('bitcoin');
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(result).not.toBeNull();
    expect(result!.id).toBe('bitcoin');
    expect(result!.current_price).toBe(84520);
    expect(result!.market_cap).toBe(1680000000000);
    expect(result!.image).toBe('https://example.com/btc.png');
  });

  it('returns null on API failure', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('API error'));

    const result = await fetchCoinById('unknown-coin');
    expect(result).toBeNull();
  });
});
