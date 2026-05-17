import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import React from 'react';

vi.mock('@/lib/theme-context', () => ({
  ThemeProvider: ({ children }: any) => <>{children}</>,
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark' }),
}));

vi.mock('@/lib/admin-context', () => ({
  AdminProvider: ({ children }: any) => <>{children}</>,
  useAdmin: () => ({ isAdmin: false, isAdminMode: false, enableAdmin: vi.fn(), disableAdmin: vi.fn(), requiresOTP: vi.fn() }),
}));

vi.mock('@/lib/websocket', () => ({
  WebSocketProvider: ({ children }: any) => <>{children}</>,
  useWebSocket: () => null,
}));

vi.mock('@/lib/binance-websocket', () => ({
  BinanceProvider: ({ children }: any) => <>{children}</>,
  useBinance: () => ({ tickers: new Map(), connected: false, refreshStats: vi.fn() }),
}));

let Providers: any;

beforeEach(async () => {
  vi.clearAllMocks();
  Providers = (await import('./providers')).default;
});

describe('Providers', () => {
  it('renders children', () => {
    render(React.createElement(Providers, null, React.createElement('div', { 'data-testid': 'child' }, 'hello')));
    expect(screen.getByTestId('child')).toBeInTheDocument();
    cleanup();
  });

  it('renders without crashing', () => {
    render(React.createElement(Providers, null, React.createElement('span', null, 'test')));
    expect(screen.getByText('test')).toBeInTheDocument();
  });

  it('catches errors via ErrorBoundary', () => {
    const ThrowError = () => { throw new Error('Boundary test error'); };
    render(React.createElement(Providers, null, React.createElement(ThrowError)));
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
    expect(screen.getByText('Boundary test error')).toBeInTheDocument();
    expect(screen.getByText('Reload Dashboard')).toBeInTheDocument();
  });

  it('shows offline banner when navigator goes offline', () => {
    render(React.createElement(Providers, null, React.createElement('div', { 'data-testid': 'child' }, 'hello')));
    expect(screen.queryByText(/You are offline/i)).not.toBeInTheDocument();
    act(() => { window.dispatchEvent(new Event('offline')); });
    expect(screen.getByText(/You are offline/i)).toBeInTheDocument();
  });

  it('hides offline banner when navigator comes back online', () => {
    render(React.createElement(Providers, null, React.createElement('div', { 'data-testid': 'child' }, 'hello')));
    act(() => { window.dispatchEvent(new Event('offline')); });
    expect(screen.getByText(/You are offline/i)).toBeInTheDocument();
    act(() => { window.dispatchEvent(new Event('online')); });
    expect(screen.queryByText(/You are offline/i)).not.toBeInTheDocument();
  });

  it('dismisses offline banner on dismiss button click', () => {
    render(React.createElement(Providers, null, React.createElement('div', { 'data-testid': 'child' }, 'hello')));
    act(() => { window.dispatchEvent(new Event('offline')); });
    expect(screen.getByText(/Dismiss/i)).toBeInTheDocument();
    act(() => { fireEvent.click(screen.getByText(/Dismiss/i)); });
    expect(screen.queryByText(/You are offline/i)).not.toBeInTheDocument();
  });

  it('shows offline from initial state when navigator.onLine is false', () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => false });
    render(React.createElement(Providers, null, React.createElement('div', { 'data-testid': 'child' }, 'hello')));
    expect(screen.getByText(/You are offline/i)).toBeInTheDocument();
    Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => true });
  });

  it('ErrorBoundary reload button calls window.location.reload', () => {
    const reloadSpy = vi.fn();
    Object.defineProperty(window, 'location', { value: { reload: reloadSpy }, writable: true });
    const ThrowError = () => { throw new Error('reload test'); };
    render(React.createElement(Providers, null, React.createElement(ThrowError)));
    fireEvent.click(screen.getByText('Reload Dashboard'));
    expect(reloadSpy).toHaveBeenCalled();
  });
});
