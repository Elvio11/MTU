import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, renderHook, act, waitFor } from '@testing-library/react';
import { BinanceProvider, useBinance, useBinanceTicker } from './binance-websocket';

let mockWs: any;
let mockFetch: ReturnType<typeof vi.fn>;
let wsInstances: any[];

beforeEach(() => {
  vi.restoreAllMocks();

  mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
    ok: true,
    json: () => Promise.resolve([]),
  } as any);

  wsInstances = [];

  class MockWebSocket {
    static OPEN = 1;
    static CONNECTING = 0;
    static CLOSING = 2;
    static CLOSED = 3;
    readyState = 1;
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onmessage: ((event: any) => void) | null = null;
    onerror: (() => void) | null = null;
    close = vi.fn();
    addEventListener = vi.fn();
    removeEventListener = vi.fn();

    constructor() {
      wsInstances.push(this);
      mockWs = this;
    }
  }

  vi.stubGlobal('WebSocket', MockWebSocket as any);
});

describe('BinanceProvider', () => {
  it('renders children', () => {
    render(React.createElement(BinanceProvider, null, React.createElement('div', { 'data-testid': 'child' }, 'hello')));
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('provides context via useBinance hook', () => {
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });
    expect(result.current).toBeDefined();
    expect(result.current.tickers).toBeDefined();
    expect(result.current.connected).toBeDefined();
    expect(typeof result.current.refreshStats).toBe('function');
  });
});

describe('useBinance', () => {
  it('returns default context (empty tickers, not connected)', () => {
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });
    expect(result.current.tickers.size).toBe(0);
    expect(result.current.connected).toBe(false);
  });
});

describe('useBinanceTicker', () => {
  it('returns undefined for unknown symbol', () => {
    const { result } = renderHook(() => useBinanceTicker('UNKNOWN'), { wrapper: BinanceProvider });
    expect(result.current).toBeUndefined();
  });

  it('returns ticker data after fallback data is loaded', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useBinanceTicker('BTC'), { wrapper: BinanceProvider });

    await waitFor(() => {
      expect(result.current).toBeDefined();
    });

    expect(result.current!.symbol).toBe('BTC');
    expect(result.current!.price).toBe(80123.17);
    expect(typeof result.current!.change24h).toBe('number');
    expect(typeof result.current!.changePercent24h).toBe('number');
  });
});

describe('refreshStats', () => {
  it('is a function', () => {
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });
    expect(typeof result.current.refreshStats).toBe('function');
  });

  it('populates tickers from API on success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([
        { symbol: 'BTCUSDT', lastPrice: '50000.00', priceChange: '100.00', priceChangePercent: '0.20', highPrice: '51000.00', lowPrice: '49000.00', volume: '1000000.00' },
        { symbol: 'ETHUSDT', lastPrice: '3000.00', priceChange: '50.00', priceChangePercent: '1.69', highPrice: '3100.00', lowPrice: '2900.00', volume: '5000000.00' },
      ]),
    } as any);

    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await act(async () => {
      await result.current.refreshStats();
    });

    expect(result.current.tickers.size).toBe(2);
    expect(result.current.tickers.get('BTC')?.price).toBe(50000);
    expect(result.current.tickers.get('BTC')?.symbol).toBe('BTC');
    expect(result.current.tickers.get('BTC')?.change24h).toBe(100);
    expect(result.current.tickers.get('BTC')?.changePercent24h).toBe(0.2);
    expect(result.current.tickers.get('BTC')?.high24h).toBe(51000);
    expect(result.current.tickers.get('BTC')?.low24h).toBe(49000);
    expect(result.current.tickers.get('BTC')?.volume24h).toBe(1000000);
    expect(result.current.tickers.get('ETH')?.price).toBe(3000);
  });

  it('uses fallback data when API returns HTTP error', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 429,
      json: () => Promise.resolve({}),
    } as any);

    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await act(async () => {
      await result.current.refreshStats();
    });

    expect(result.current.tickers.size).toBeGreaterThan(0);
    expect(result.current.tickers.get('BTC')?.price).toBe(80123.17);
  });

  it('uses fallback data when API returns non-array response', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ symbol: 'BTCUSDT' }),
    } as any);

    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await act(async () => {
      await result.current.refreshStats();
    });

    expect(result.current.tickers.size).toBeGreaterThan(0);
    expect(result.current.tickers.get('BTC')?.price).toBe(80123.17);
  });

  it('uses fallback data when API throws network error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await act(async () => {
      await result.current.refreshStats();
    });

    expect(result.current.tickers.size).toBe(26);
    expect(result.current.tickers.get('BTC')?.price).toBe(80123.17);
    expect(result.current.tickers.get('ETH')?.price).toBe(2356.48);
  });

  it('does nothing when API returns empty tickers', async () => {
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await act(async () => {
      await result.current.refreshStats();
    });

    expect(result.current.tickers.size).toBe(0);
  });

  it('preserves existing prices when API returns new stats', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await waitFor(() => {
      expect(result.current.tickers.size).toBe(26);
    });

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([
        { symbol: 'BTCUSDT', lastPrice: '90000.00', priceChange: '200.00', priceChangePercent: '0.22', highPrice: '92000.00', lowPrice: '88000.00', volume: '30000000.00' },
      ]),
    } as any);

    await act(async () => {
      await result.current.refreshStats();
    });

    expect(result.current.tickers.get('BTC')?.price).toBe(80123.17);
    expect(result.current.tickers.get('BTC')?.change24h).toBe(200);
    expect(result.current.tickers.get('BTC')?.changePercent24h).toBe(0.22);
    expect(result.current.tickers.get('BTC')?.high24h).toBe(92000);
    expect(result.current.tickers.get('BTC')?.low24h).toBe(88000);
    expect(result.current.tickers.size).toBe(26);
  });
});

describe('WebSocket connection lifecycle', () => {
  it('starts disconnected', () => {
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });
    expect(result.current.connected).toBe(false);
  });

  it('sets connected to true on open', () => {
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });
    act(() => { mockWs.onopen(); });
    expect(result.current.connected).toBe(true);
  });

  it('sets connected to false on close', () => {
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });
    act(() => { mockWs.onopen(); });
    act(() => { mockWs.onclose(); });
    expect(result.current.connected).toBe(false);
  });

  it('reconnects on close within max attempts', () => {
    vi.useFakeTimers();

    renderHook(() => useBinance(), { wrapper: BinanceProvider });

    expect(wsInstances.length).toBe(1);

    wsInstances[0].readyState = 3;
    act(() => { wsInstances[0].onclose(); });
    act(() => { vi.advanceTimersByTime(3000); });

    expect(wsInstances.length).toBe(2);

    vi.useRealTimers();
  });

  it('stops reconnecting after max attempts', () => {
    vi.useFakeTimers();

    renderHook(() => useBinance(), { wrapper: BinanceProvider });

    for (let i = 0; i < 5; i++) {
      const ws = wsInstances[i];
      if (!ws) break;
      ws.readyState = 3;
      act(() => { ws.onclose(); });
      act(() => { vi.advanceTimersByTime(3000); });
    }

    const countAfter5th = wsInstances.length;

    const lastWs = wsInstances[wsInstances.length - 1];
    if (lastWs) {
      lastWs.readyState = 3;
      act(() => { lastWs.onclose(); });
      act(() => { vi.advanceTimersByTime(3000); });
    }

    expect(wsInstances.length).toBe(countAfter5th);

    vi.useRealTimers();
  });

  it('does not reconnect if close fires but connection is still open', () => {
    vi.useFakeTimers();

    renderHook(() => useBinance(), { wrapper: BinanceProvider });

    act(() => { wsInstances[0].onclose(); });
    act(() => { vi.advanceTimersByTime(3000); });

    expect(wsInstances.length).toBe(1);

    vi.useRealTimers();
  });

  it('increments reconnect attempts on error', () => {
    vi.useFakeTimers();

    renderHook(() => useBinance(), { wrapper: BinanceProvider });

    wsInstances[0].readyState = 3;
    act(() => { wsInstances[0].onerror(); });
    act(() => { wsInstances[0].onclose(); });
    act(() => { vi.advanceTimersByTime(3000); });

    expect(wsInstances.length).toBe(2);

    vi.useRealTimers();
  });
});

describe('WebSocket message handling', () => {
  it('processes valid trade message and updates tickers via interval', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    act(() => { mockWs.onopen(); });
    act(() => {
      mockWs.onmessage({ data: JSON.stringify({ s: 'BTCUSDT', p: '50000.00' }) });
    });

    act(() => { vi.advanceTimersByTime(250); });

    expect(result.current.tickers.size).toBe(1);
    const btc = result.current.tickers.get('BTC');
    expect(btc?.symbol).toBe('BTC');
    expect(btc?.price).toBe(50000);
    expect(btc?.change24h).toBe(0);
    expect(btc?.changePercent24h).toBe(0);
    expect(btc?.high24h).toBe(50000);
    expect(btc?.low24h).toBe(50000);
    expect(btc?.volume24h).toBe(0);

    vi.useRealTimers();
  });

  it('processes multiple trade messages', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    act(() => { mockWs.onopen(); });
    act(() => {
      mockWs.onmessage({ data: JSON.stringify({ s: 'BTCUSDT', p: '50000.00' }) });
      mockWs.onmessage({ data: JSON.stringify({ s: 'ETHUSDT', p: '3000.00' }) });
      mockWs.onmessage({ data: JSON.stringify({ s: 'SOLUSDT', p: '150.00' }) });
    });

    act(() => { vi.advanceTimersByTime(250); });

    expect(result.current.tickers.size).toBe(3);
    expect(result.current.tickers.get('BTC')?.price).toBe(50000);
    expect(result.current.tickers.get('ETH')?.price).toBe(3000);
    expect(result.current.tickers.get('SOL')?.price).toBe(150);

    vi.useRealTimers();
  });

  it('ignores message without s field', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    act(() => { mockWs.onopen(); });
    act(() => {
      mockWs.onmessage({ data: JSON.stringify({ e: 'trade', E: 123456789 }) });
    });

    act(() => { vi.advanceTimersByTime(250); });

    expect(result.current.tickers.size).toBe(0);

    vi.useRealTimers();
  });

  it('handles invalid JSON message gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.useFakeTimers();
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    act(() => { mockWs.onopen(); });
    act(() => {
      mockWs.onmessage({ data: 'not valid json' });
    });

    act(() => { vi.advanceTimersByTime(250); });

    expect(result.current.tickers.size).toBe(0);
    expect(consoleSpy).toHaveBeenCalledWith('Binance WS parse error:', expect.any(SyntaxError));

    vi.useRealTimers();
    consoleSpy.mockRestore();
  });

  it('uses existing pending data for change24h when no ticker exists', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    act(() => { mockWs.onopen(); });
    act(() => {
      mockWs.onmessage({ data: JSON.stringify({ s: 'BTCUSDT', p: '50000.00' }) });
    });

    act(() => { vi.advanceTimersByTime(250); });

    expect(result.current.tickers.get('BTC')?.change24h).toBe(0);
    expect(result.current.tickers.get('BTC')?.high24h).toBe(50000);
    expect(result.current.tickers.get('BTC')?.low24h).toBe(50000);

    vi.useRealTimers();
  });
});

describe('cleanup', () => {
  it('closes WebSocket on unmount', () => {
    const { unmount } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    expect(mockWs.close).not.toHaveBeenCalled();

    unmount();

    expect(mockWs.close).toHaveBeenCalled();
  });

  it('clears reconnect timer on unmount after close', () => {
    vi.useFakeTimers();

    const { unmount } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    act(() => { wsInstances[0].onclose(); });

    unmount();

    act(() => { vi.advanceTimersByTime(3000); });

    expect(wsInstances.length).toBe(1);

    vi.useRealTimers();
  });
});

describe('init ticker loading', () => {
  it('loads initial tickers from API on mount when data is available', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([
        { symbol: 'BTCUSDT', lastPrice: '50000.00', priceChange: '100.00', priceChangePercent: '0.20', highPrice: '51000.00', lowPrice: '49000.00', volume: '1000000.00' },
        { symbol: 'ETHUSDT', lastPrice: '3000.00', priceChange: '50.00', priceChangePercent: '1.69', highPrice: '3100.00', lowPrice: '2900.00', volume: '5000000.00' },
        { symbol: 'SOLUSDT', lastPrice: '150.00', priceChange: '5.00', priceChangePercent: '3.45', highPrice: '155.00', lowPrice: '145.00', volume: '2000000.00' },
      ]),
    } as any);

    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await waitFor(() => {
      expect(result.current.tickers.size).toBeGreaterThan(0);
    });

    expect(result.current.tickers.size).toBe(3);
    expect(result.current.tickers.get('BTC')?.price).toBe(50000);
    expect(result.current.tickers.get('ETH')?.price).toBe(3000);
    expect(result.current.tickers.get('SOL')?.price).toBe(150);
  });

  it('loads fallback tickers when API fails on init', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await waitFor(() => {
      expect(result.current.tickers.size).toBeGreaterThan(0);
    });

    expect(result.current.tickers.get('BTC')?.price).toBe(80123.17);
    expect(result.current.tickers.get('BTC')?.symbol).toBe('BTC');
    expect(result.current.tickers.size).toBe(26);
  });

  it('only loads initial tickers once (statsFetched guard)', async () => {
    let fetchCount = 0;
    mockFetch.mockImplementation(() => {
      fetchCount++;
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as any);
    });

    const { rerender } = renderHook(() => useBinance(), { wrapper: BinanceProvider });

    await vi.waitFor(() => {
      expect(fetchCount).toBe(1);
    });

    rerender();

    expect(fetchCount).toBe(1);
  });
});
