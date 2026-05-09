"use client";

import React, { useState, useEffect, Component, ReactNode } from 'react';
import { WebSocketProvider } from '@/lib/websocket';
import { BinanceProvider } from '@/lib/binance-websocket';
import { ThemeProvider } from '@/lib/theme-context';
import { AdminProvider } from '@/lib/admin-context';

class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Dashboard Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-mtus-bg flex items-center justify-center p-4">
          <div className="bg-mtus-card p-6 rounded-xl border border-red-700 max-w-md">
            <h1 className="text-xl font-bold text-red-400 mb-4">Something went wrong</h1>
            <p className="text-slate-400 mb-4">{this.state.error?.message || 'An unexpected error occurred'}</p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-mtus-accent text-white rounded-lg hover:bg-opacity-90"
            >
              Reload Dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function NetworkStatusProvider({ children }: { children: ReactNode }) {
  const [showBanner, setShowBanner] = useState(() => {
    if (typeof window === 'undefined') return false;
    return !navigator.onLine;
  });

  useEffect(() => {
    const handleOnline = () => {
      setShowBanner(false);
    };
    const handleOffline = () => {
      setShowBanner(true);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return (
    <>
      {showBanner && (
        <div className="fixed top-0 left-0 right-0 bg-yellow-600 text-white px-4 py-2 text-center z-50">
          ⚠️ You are offline. Some features may not work.
          <button 
            onClick={() => setShowBanner(false)} 
            className="ml-4 text-sm underline"
          >
            Dismiss
          </button>
        </div>
      )}
      <div className={showBanner ? 'mt-8' : ''}>
        {children}
      </div>
    </>
  );
}

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AdminProvider>
          <NetworkStatusProvider>
            <WebSocketProvider>
              <BinanceProvider>
                {children}
              </BinanceProvider>
            </WebSocketProvider>
          </NetworkStatusProvider>
        </AdminProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}