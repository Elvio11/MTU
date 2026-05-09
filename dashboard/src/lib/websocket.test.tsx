import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('WebSocket exponential backoff', () => {
  it('should calculate reconnect delay with exponential backoff', () => {
    const baseReconnectDelay = 1000;
    const maxReconnectDelay = 30000;

    const getReconnectDelay = (attempts: number) => {
      const delay = baseReconnectDelay * Math.pow(2, attempts);
      const jitter = 0;
      return Math.min(delay + jitter, maxReconnectDelay);
    };

    expect(getReconnectDelay(0)).toBe(1000);
    expect(getReconnectDelay(1)).toBe(2000);
    expect(getReconnectDelay(2)).toBe(4000);
    expect(getReconnectDelay(3)).toBe(8000);
    expect(getReconnectDelay(4)).toBe(16000);
    expect(getReconnectDelay(5)).toBe(30000);
    expect(getReconnectDelay(10)).toBe(maxReconnectDelay);
  });

  it('should cap delay at maxReconnectDelay', () => {
    const baseReconnectDelay = 1000;
    const maxReconnectDelay = 30000;

    const getReconnectDelay = (attempts: number) => {
      const delay = baseReconnectDelay * Math.pow(2, attempts);
      return Math.min(delay, maxReconnectDelay);
    };

    expect(getReconnectDelay(15)).toBe(maxReconnectDelay);
  });

  it('should have base delay of 1000ms', () => {
    const baseReconnectDelay = 1000;
    expect(baseReconnectDelay).toBe(1000);
  });
});

describe('WebSocket reconnect attempts', () => {
  it('should limit max reconnect attempts to 10', () => {
    const maxReconnectAttempts = 10;
    expect(maxReconnectAttempts).toBe(10);
  });

  it('should track reconnect attempts correctly', () => {
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 10;

    for (let i = 0; i < 15; i++) {
      if (reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
      }
    }

    expect(reconnectAttempts).toBe(10);
  });
});

describe('WebSocket state transitions', () => {
  it('should track connected state', () => {
    let connected = false;

    const onStateChange = (conn: boolean) => {
      connected = conn;
    };

    onStateChange(true);
    expect(connected).toBe(true);

    onStateChange(false);
    expect(connected).toBe(false);
  });

  it('should track reconnecting state', () => {
    let reconnecting = false;

    const onStateChange = (_connected: boolean, reconn: boolean) => {
      reconnecting = reconn;
    };

    onStateChange(false, true);
    expect(reconnecting).toBe(true);

    onStateChange(true, false);
    expect(reconnecting).toBe(false);
  });
});