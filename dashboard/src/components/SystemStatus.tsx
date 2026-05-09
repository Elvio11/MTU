'use client';

import { useEffect, useState } from 'react';
import { useWebSocket } from '@/lib/websocket';
import { Server, Shield, Activity, AlertCircle } from 'lucide-react';

interface RPCStatus {
  helius: { state: string; failures: number; latency?: number };
  quicknode: { state: string; failures: number; latency?: number };
  alchemy: { state: string; failures: number; latency?: number };
}

interface RateLimiterStatus {
  tradesThisHour: number;
  maxTradesPerHour: number;
  activePositions: number;
  maxPositions: number;
  canTrade: boolean;
}

interface CircuitBreakerStatus {
  name: string;
  state: 'closed' | 'open' | 'half_open';
  failures: number;
  lastChange: string;
}

interface SystemStatusProps {
  compact?: boolean;
}

export default function SystemStatus({ compact = false }: SystemStatusProps) {
  const [rpcStatus, setRpcStatus] = useState<RPCStatus | null>(null);
  const [rateLimiter, setRateLimiter] = useState<RateLimiterStatus | null>(null);
  const [circuitBreakers, setCircuitBreakers] = useState<CircuitBreakerStatus[]>([]);
  const ws = useWebSocket();

  useEffect(() => {
    if (!ws) return;

    const handleRPCStatus = (payload: unknown) => {
      setRpcStatus(payload as RPCStatus);
    };

    const handleRateLimiter = (payload: unknown) => {
      setRateLimiter(payload as RateLimiterStatus);
    };

    const handleCircuitBreaker = (payload: unknown) => {
      const data = payload as { name: string; state: string; failures: number };
      setCircuitBreakers(prev => {
        const existing = prev.findIndex(cb => cb.name === data.name);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = {
            ...data,
            state: data.state as 'closed' | 'open' | 'half_open',
            lastChange: new Date().toISOString(),
          };
          return updated;
        }
        return [...prev, {
          name: data.name,
          state: data.state as 'closed' | 'open' | 'half_open',
          failures: data.failures,
          lastChange: new Date().toISOString(),
        }];
      });
    };

    ws.subscribe('rpc_status', handleRPCStatus);
    ws.subscribe('rate_limit', handleRateLimiter);
    ws.subscribe('circuit_breaker', handleCircuitBreaker);

    return () => {
      ws.unsubscribe('rpc_status', handleRPCStatus);
      ws.unsubscribe('rate_limit', handleRateLimiter);
      ws.unsubscribe('circuit_breaker', handleCircuitBreaker);
    };
  }, [ws]);

  const getStateColor = (state: string) => {
    switch (state) {
      case 'closed':
        return 'text-profit';
      case 'open':
        return 'text-loss';
      case 'half_open':
        return 'text-yellow-500';
      default:
        return 'text-slate-400';
    }
  };

  const getStateIcon = (state: string) => {
    switch (state) {
      case 'closed':
        return <Shield size={14} className="text-profit" />;
      case 'open':
        return <AlertCircle size={14} className="text-loss" />;
      case 'half_open':
        return <Activity size={14} className="text-yellow-500" />;
      default:
        return <Server size={14} className="text-slate-400" />;
    }
  };

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-sm">
        {rpcStatus ? (
          Object.entries(rpcStatus).map(([name, status]) => (
            <div key={name} className="flex items-center gap-1">
              {getStateIcon(status.state)}
              <span className="text-slate-400 capitalize">{name}</span>
            </div>
          ))
        ) : (
          <span className="text-slate-500">RPC: Connecting...</span>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* RPC Status */}
      <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
        <div className="flex items-center gap-2 mb-3">
          <Server size={18} className="text-mtus-accent" />
          <h3 className="text-lg font-semibold text-white">RPC Endpoints</h3>
        </div>
        
        {rpcStatus ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {Object.entries(rpcStatus).map(([name, status]) => (
              <div key={name} className="p-3 bg-slate-800 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-white capitalize">{name}</span>
                  <div className="flex items-center gap-1">
                    {getStateIcon(status.state)}
                    <span className={`text-sm ${getStateColor(status.state)}`}>
                      {status.state.replace('_', ' ')}
                    </span>
                  </div>
                </div>
                <div className="text-xs text-slate-500">
                  Failures: {status.failures}
                  {status.latency && ` | Latency: ${status.latency}ms`}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-slate-500 text-center py-4">
            Connecting to RPC status...
          </div>
        )}
      </div>

      {/* Rate Limiter Status */}
      <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={18} className="text-mtus-accent" />
          <h3 className="text-lg font-semibold text-white">Rate Limiter</h3>
        </div>
        
        {rateLimiter ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 bg-slate-800 rounded-lg">
              <div className="text-xs text-slate-500 mb-1">Trades This Hour</div>
              <div className="text-xl font-bold text-white">
                {rateLimiter.tradesThisHour}
                <span className="text-sm text-slate-500">/{rateLimiter.maxTradesPerHour}</span>
              </div>
            </div>
            <div className="p-3 bg-slate-800 rounded-lg">
              <div className="text-xs text-slate-500 mb-1">Active Positions</div>
              <div className="text-xl font-bold text-white">
                {rateLimiter.activePositions}
                <span className="text-sm text-slate-500">/{rateLimiter.maxPositions}</span>
              </div>
            </div>
            <div className="p-3 bg-slate-800 rounded-lg">
              <div className="text-xs text-slate-500 mb-1">Can Trade</div>
              <div className={`text-xl font-bold ${rateLimiter.canTrade ? 'text-profit' : 'text-loss'}`}>
                {rateLimiter.canTrade ? 'Yes' : 'No'}
              </div>
            </div>
            <div className="p-3 bg-slate-800 rounded-lg">
              <div className="text-xs text-slate-500 mb-1">Capacity</div>
              <div className="text-xl font-bold text-white">
                {Math.round((1 - rateLimiter.tradesThisHour / rateLimiter.maxTradesPerHour) * 100)}%
              </div>
            </div>
          </div>
        ) : (
          <div className="text-slate-500 text-center py-4">
            Connecting to rate limiter...
          </div>
        )}
      </div>

      {/* Circuit Breakers */}
      {circuitBreakers.length > 0 && (
        <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
          <div className="flex items-center gap-2 mb-3">
            <Shield size={18} className="text-mtus-accent" />
            <h3 className="text-lg font-semibold text-white">Circuit Breakers</h3>
          </div>
          
          <div className="space-y-2">
            {circuitBreakers.map((cb, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-slate-800 rounded-lg">
                <div className="flex items-center gap-2">
                  {getStateIcon(cb.state)}
                  <span className="font-medium text-white">{cb.name}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className={`text-sm ${getStateColor(cb.state)}`}>
                    {cb.state.replace('_', ' ')}
                  </span>
                  <span className="text-xs text-slate-500">
                    {cb.failures} failures
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}