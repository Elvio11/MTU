import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import { WebSocketProvider, useWebSocket, MTUSWebSocket } from './websocket';

let mockInstances: any[];

beforeEach(() => {
  mockInstances = [];

  const MockWS: any = vi.fn(function (this: any, url: string) {
    this.url = url;
    this.readyState = MockWS.CONNECTING;
    this.send = vi.fn();
    this.close = vi.fn(() => {
      this.readyState = MockWS.CLOSED;
    });
    this._onopen = null;
    this._onclose = null;
    this._onerror = null;
    this._onmessage = null;

    Object.defineProperty(this, 'onopen', {
      get: () => this._onopen,
      set: (fn) => {
        this._onopen = fn
          ? (...args: any[]) => {
              this.readyState = MockWS.OPEN;
              return fn(...args);
            }
          : null;
      },
      configurable: true,
    });
    Object.defineProperty(this, 'onclose', {
      get: () => this._onclose,
      set: (fn) => {
        this._onclose = fn
          ? (...args: any[]) => {
              this.readyState = MockWS.CLOSED;
              return fn(...args);
            }
          : null;
      },
      configurable: true,
    });
    Object.defineProperty(this, 'onerror', {
      get: () => this._onerror,
      set: (fn) => {
        this._onerror = fn ? (...args: any[]) => fn(...args) : null;
      },
      configurable: true,
    });
    Object.defineProperty(this, 'onmessage', {
      get: () => this._onmessage,
      set: (fn) => {
        this._onmessage = fn ? (...args: any[]) => fn(...args) : null;
      },
      configurable: true,
    });

    mockInstances.push(this);
  });
  MockWS.OPEN = 1;
  MockWS.CONNECTING = 0;
  MockWS.CLOSED = 3;
  MockWS.CLOSING = 2;

  vi.stubGlobal('WebSocket', MockWS);
  vi.stubEnv('NODE_ENV', 'test');
  vi.stubEnv('NEXT_PUBLIC_WS_URL', undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('MTUSWebSocket', () => {
  describe('constructor', () => {
    it('uses provided URL', () => {
      const ws = new MTUSWebSocket('ws://custom:9000');
      ws.connect();
      expect(mockInstances[0].url).toBe('ws://custom:9000');
    });

    it('uses NEXT_PUBLIC_WS_URL env var when set', () => {
      process.env.NEXT_PUBLIC_WS_URL = 'ws://env:1234';
      const ws = new MTUSWebSocket();
      ws.connect();
      expect(mockInstances[0].url).toBe('ws://env:1234');
    });

    it('falls back to default URL when nothing provided', () => {
      const ws = new MTUSWebSocket();
      ws.connect();
      expect(mockInstances[0].url).toBe('ws://localhost:4001');
    });

    it('env var takes precedence over constructor argument', () => {
      process.env.NEXT_PUBLIC_WS_URL = 'ws://env:1234';
      const ws = new MTUSWebSocket('ws://arg:5678');
      ws.connect();
      expect(mockInstances[0].url).toBe('ws://env:1234');
    });
  });

  describe('connect', () => {
    it('creates a WebSocket with the configured URL', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      expect(mockInstances).toHaveLength(1);
      expect(mockInstances[0].url).toBe('ws://test:8080');
    });

    it('skips if already connected and readyState is OPEN', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].readyState = WebSocket.OPEN;
      ws.connect();
      expect(mockInstances).toHaveLength(1);
    });

    it('calls onStateChange with connected=false, reconnecting=false on first connect', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.setStateChangeCallback(cb);
      ws.connect();
      expect(cb).toHaveBeenCalledWith(false, false);
    });

    it('calls onStateChange with reconnecting=true on reconnect', () => {
      vi.useFakeTimers();
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.setStateChangeCallback(cb);
      ws.connect();
      cb.mockClear();
      mockInstances[0].onclose?.({});
      expect(cb).toHaveBeenCalledWith(false, true);
    });

    it('onopen sets connected state and notifies', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.setStateChangeCallback(cb);
      ws.connect();
      cb.mockClear();
      mockInstances[0].onopen?.({});
      expect(cb).toHaveBeenCalledWith(true, false);
      expect(ws.isConnected()).toBe(true);
    });

    it('onopen resets reconnectAttempts', () => {
      vi.useFakeTimers();
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onclose?.({});
      vi.advanceTimersByTime(5000);
      mockInstances[1].onopen?.({});
      expect(ws.isConnected()).toBe(true);
    });

    it('onopen sends auth token when set', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.setAuthToken('my-token');
      ws.connect();
      mockInstances[0].onopen?.({});
      expect(mockInstances[0].send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'auth', token: 'my-token' }),
      );
    });

    it('onopen does not send auth if no token set', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onopen?.({});
      expect(mockInstances[0].send).not.toHaveBeenCalled();
    });

    it('onmessage parses JSON, notifies listeners, updates lastMessage', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.subscribe('greeting', cb);
      ws.connect();
      mockInstances[0].onmessage?.({
        data: JSON.stringify({ type: 'greeting', payload: 'hello' }),
      });
      expect(cb).toHaveBeenCalledWith('hello');
      expect(ws.getLastMessage()).toEqual({ type: 'greeting', payload: 'hello' });
    });

    it('onmessage handles malformed JSON silently in test env', () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onmessage?.({ data: 'not-json' });
      expect(ws.getLastMessage()).toBeNull();
      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    });

    it('onmessage logs parse error in development mode', () => {
      vi.stubEnv('NODE_ENV', 'development');
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onmessage?.({ data: 'bad-json' });
      expect(spy).toHaveBeenCalled();
      spy.mockRestore();
    });

    it('onerror does not throw', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      expect(() => mockInstances[0].onerror?.({})).not.toThrow();
    });

    it('onerror increments reconnectAttempts', () => {
      vi.useFakeTimers();
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onerror?.({});
      mockInstances[0].onerror?.({});
      mockInstances[0].onerror?.({});
      mockInstances[0].onclose?.({});
      vi.advanceTimersByTime(35000);
      expect(mockInstances.length).toBeGreaterThanOrEqual(2);
    });

    it('onclose schedules reconnection', () => {
      vi.useFakeTimers();
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onclose?.({});
      vi.advanceTimersByTime(5000);
      expect(mockInstances.length).toBe(2);
    });

    it('onclose stops reconnecting after max attempts', () => {
      vi.useFakeTimers();
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();

      for (let i = 0; i < 10; i++) {
        const idx = mockInstances.length - 1;
        mockInstances[idx].onclose?.({});
        vi.advanceTimersByTime(35000);
      }

      expect(mockInstances.length).toBeLessThanOrEqual(10);
    });

    it('onclose notifies state with reconnecting=true', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.setStateChangeCallback(cb);
      ws.connect();
      cb.mockClear();
      mockInstances[0].onclose?.({});
      expect(cb).toHaveBeenCalledWith(false, true);
    });

    it('onclose notifies state with reconnecting=false when max attempts reached', () => {
      vi.useFakeTimers();
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.setStateChangeCallback(cb);
      ws.connect();

      for (let i = 0; i < 10; i++) {
        const idx = mockInstances.length - 1;
        mockInstances[idx].onclose?.({});
        vi.advanceTimersByTime(35000);
      }

      const lastCall = cb.mock.calls[cb.mock.calls.length - 1];
      expect(lastCall).toEqual([false, false]);
    });

    it('logs in development mode on connection error', () => {
      const ThrowingWS: any = vi.fn(() => {
        throw new Error('conn failed');
      });
      ThrowingWS.OPEN = 1;
      ThrowingWS.CONNECTING = 0;
      ThrowingWS.CLOSED = 3;
      ThrowingWS.CLOSING = 2;
      vi.stubGlobal('WebSocket', ThrowingWS);
      vi.stubEnv('NODE_ENV', 'development');
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();

      expect(spy).toHaveBeenCalled();
      spy.mockRestore();
    });

    it('handles WebSocket constructor exception and schedules reconnect', () => {
      vi.useFakeTimers();
      const ThrowingWS: any = vi.fn(() => {
        throw new Error('conn failed');
      });
      ThrowingWS.OPEN = 1;
      ThrowingWS.CONNECTING = 0;
      ThrowingWS.CLOSED = 3;
      ThrowingWS.CLOSING = 2;
      vi.stubGlobal('WebSocket', ThrowingWS);

      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();

      expect(ThrowingWS).toHaveBeenCalled();
      vi.advanceTimersByTime(5000);
      expect(ThrowingWS).toHaveBeenCalledTimes(2);
    });
  });

  describe('disconnect', () => {
    it('closes the WebSocket and sets ws to null', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      ws.disconnect();
      expect(mockInstances[0].close).toHaveBeenCalled();
    });

    it('clears reconnect timer', () => {
      vi.useFakeTimers();
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onclose?.({});
      ws.disconnect();
      vi.advanceTimersByTime(50000);
      expect(mockInstances).toHaveLength(1);
    });

    it('sets connected to false', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onopen?.({});
      ws.disconnect();
      expect(ws.isConnected()).toBe(false);
    });

    it('calls onStateChange with connected=false, reconnecting=false', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.setStateChangeCallback(cb);
      cb.mockClear();
      ws.disconnect();
      expect(cb).toHaveBeenCalledWith(false, false);
    });

    it('is safe to call when not connected', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      expect(() => ws.disconnect()).not.toThrow();
    });
  });

  describe('send', () => {
    it('sends JSON string when connected', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onopen?.({});
      ws.send({ hello: 'world' });
      expect(mockInstances[0].send).toHaveBeenCalledWith(
        JSON.stringify({ hello: 'world' }),
      );
    });

    it('does nothing when ws is null', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      expect(() => ws.send({ data: 'test' })).not.toThrow();
    });

    it('does nothing when socket is not OPEN', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      ws.send({ data: 'test' });
      expect(mockInstances[0].send).not.toHaveBeenCalled();
    });
  });

  describe('subscribe / unsubscribe', () => {
    it('adds listener and invokes it on matching message', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.subscribe('test', cb);
      ws.connect();
      mockInstances[0].onmessage?.({
        data: JSON.stringify({ type: 'test', payload: 42 }),
      });
      expect(cb).toHaveBeenCalledWith(42);
    });

    it('does not invoke listener for non-matching type', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.subscribe('type_a', cb);
      ws.connect();
      mockInstances[0].onmessage?.({
        data: JSON.stringify({ type: 'type_b', payload: 42 }),
      });
      expect(cb).not.toHaveBeenCalled();
    });

    it('removes listener so it is no longer invoked', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.subscribe('test', cb);
      ws.unsubscribe('test', cb);
      ws.connect();
      mockInstances[0].onmessage?.({
        data: JSON.stringify({ type: 'test', payload: 42 }),
      });
      expect(cb).not.toHaveBeenCalled();
    });

    it('unsubscribe from nonexistent type does not throw', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      expect(() => ws.unsubscribe('missing', vi.fn())).not.toThrow();
    });

    it('unsubscribe callback not in list does not throw', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.subscribe('test', vi.fn());
      expect(() => ws.unsubscribe('test', vi.fn())).not.toThrow();
    });

    it('multiple listeners on same type all receive message', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb1 = vi.fn();
      const cb2 = vi.fn();
      ws.subscribe('test', cb1);
      ws.subscribe('test', cb2);
      ws.connect();
      mockInstances[0].onmessage?.({
        data: JSON.stringify({ type: 'test', payload: 'data' }),
      });
      expect(cb1).toHaveBeenCalledWith('data');
      expect(cb2).toHaveBeenCalledWith('data');
    });
  });

  describe('setAuthToken', () => {
    it('stores token and sends auth message if already connected', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onopen?.({});
      mockInstances[0].send.mockClear();
      ws.setAuthToken('new-token');
      expect(mockInstances[0].send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'auth', token: 'new-token' }),
      );
    });

    it('stores token but does not send if not connected', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.setAuthToken('token-while-disconnected');
      expect(ws.isConnected()).toBe(false);
    });

    it('clearing token to null does not send', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onopen?.({});
      mockInstances[0].send.mockClear();
      ws.setAuthToken(null);
      expect(mockInstances[0].send).not.toHaveBeenCalled();
    });
  });

  describe('isConnected', () => {
    it('returns false initially', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      expect(ws.isConnected()).toBe(false);
    });

    it('returns true when connected and readyState is OPEN', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onopen?.({});
      expect(ws.isConnected()).toBe(true);
    });

    it('returns false after disconnect', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onopen?.({});
      ws.disconnect();
      expect(ws.isConnected()).toBe(false);
    });
  });

  describe('getLastMessage', () => {
    it('returns null initially', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      expect(ws.getLastMessage()).toBeNull();
    });

    it('returns the last received message', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      ws.connect();
      mockInstances[0].onmessage?.({
        data: JSON.stringify({ type: 'a', payload: 1 }),
      });
      mockInstances[0].onmessage?.({
        data: JSON.stringify({ type: 'b', payload: 2 }),
      });
      expect(ws.getLastMessage()).toEqual({ type: 'b', payload: 2 });
    });
  });

  describe('setStateChangeCallback', () => {
    it('stores callback and fires it on connect', () => {
      const ws = new MTUSWebSocket('ws://test:8080');
      const cb = vi.fn();
      ws.setStateChangeCallback(cb);
      ws.connect();
      expect(cb).toHaveBeenCalled();
    });
  });
});

describe('WebSocketProvider', () => {
  it('initializes with default connection state', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper: WebSocketProvider });
    expect(result.current!.connected).toBe(false);
    expect(typeof result.current!.reconnecting).toBe('boolean');
    expect(result.current!.lastMessage).toBeNull();
  });

  it('renders children', () => {
    render(React.createElement(WebSocketProvider, null, React.createElement('div', { 'data-testid': 'child' }, 'hello')));
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('handles provider unmount without error', () => {
    const { unmount } = render(
      React.createElement(WebSocketProvider, null, React.createElement('div')),
    );
    expect(() => unmount()).not.toThrow();
  });

  it('subscribe and unsubscribe do not throw', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper: WebSocketProvider });
    const cb = vi.fn();
    expect(() => result.current!.subscribe('test_type', cb)).not.toThrow();
    expect(() => result.current!.unsubscribe('test_type', cb)).not.toThrow();
  });

  it('unsubscribe nonexistent type does not throw', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper: WebSocketProvider });
    expect(() => result.current!.unsubscribe('missing_type', vi.fn())).not.toThrow();
  });

  it('multiple subscribe/unsubscribe cycles', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper: WebSocketProvider });
    const cb1 = vi.fn();
    const cb2 = vi.fn();
    result.current!.subscribe('multi_a', cb1);
    result.current!.subscribe('multi_a', cb2);
    result.current!.subscribe('multi_b', cb1);
    result.current!.unsubscribe('multi_a', cb1);
    result.current!.unsubscribe('multi_a', cb2);
    result.current!.unsubscribe('multi_b', cb1);
    result.current!.unsubscribe('multi_a', cb1);
  });

  it('send and setAuthToken do not throw', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper: WebSocketProvider });
    expect(() => result.current!.send({ foo: 'bar' })).not.toThrow();
    expect(() => result.current!.setAuthToken('secret')).not.toThrow();
    expect(() => result.current!.setAuthToken(null)).not.toThrow();
  });
});

describe('useWebSocket', () => {
  it('has subscribe, unsubscribe, send, connected, reconnecting, lastMessage, setAuthToken', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper: WebSocketProvider });
    expect(result.current).not.toBeNull();
    expect(typeof result.current!.subscribe).toBe('function');
    expect(typeof result.current!.unsubscribe).toBe('function');
    expect(typeof result.current!.send).toBe('function');
    expect(typeof result.current!.setAuthToken).toBe('function');
    expect(typeof result.current!.connected).toBe('boolean');
  });

  it('returns null outside provider', () => {
    const { result } = renderHook(() => useWebSocket());
    expect(result.current).toBeNull();
  });
});
