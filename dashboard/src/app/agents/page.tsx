'use client';

import { useEffect, useState } from 'react';
import { useWebSocket } from '@/lib/websocket';
import AgentCard from '@/components/AgentCard';
import { Activity, Clock, TrendingUp, AlertTriangle } from 'lucide-react';

interface Agent {
  id: string;
  name: string;
  status: 'healthy' | 'unhealthy' | 'starting' | 'paused';
  lastHeartbeat: string;
  tradesToday?: number;
  pnlToday?: number;
  uptime?: number;
  messagesProcessed?: number;
  errors?: number;
  lastError?: string;
  avgResponseTime?: number;
}

interface EnvelopePayload {
  agent_id: string;
  event_type: string;
  payload: {
    status?: string;
    daily_pnl?: number;
    [key: string]: unknown;
  };
  correlation_id: string;
  envelope_id: string;
  [key: string]: unknown;
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const ws = useWebSocket();

  useEffect(() => {
    if (!ws) return;

    const handleHealth = (payload: unknown) => {
      console.log('[agents] health_check payload:', JSON.stringify(payload));
      const data = payload as EnvelopePayload;
      const innerPayload = data.payload as Record<string, unknown>;
      const status = (innerPayload?.status as string) || 'unknown';
      console.log('[agents] extracted status:', status, 'agent_id:', data.agent_id);
      const normalizedStatus: 'healthy' | 'unhealthy' | 'starting' | 'paused' = 
        status === 'healthy' ? 'healthy' : 
        status === 'unhealthy' ? 'unhealthy' :
        status === 'starting' ? 'starting' :
        status === 'paused' ? 'paused' : 'unhealthy';
      
      setAgents(prev => {
        const existing = prev.find(a => a.id === data.agent_id);
        if (existing) {
          return prev.map(a => 
            a.id === data.agent_id ? { 
              ...a, 
              status: normalizedStatus, 
              lastHeartbeat: '0s ago',
              pnlToday: (innerPayload?.daily_pnl as number) ?? a.pnlToday,
            } : a
          );
        }
        return [...prev, {
          id: data.agent_id,
          name: data.agent_id,
          status: normalizedStatus,
          lastHeartbeat: '0s ago',
          tradesToday: 0,
          pnlToday: innerPayload?.daily_pnl as number | undefined,
        }];
      });
    };

    ws.subscribe('health_check', handleHealth);
    ws.subscribe('agent_health', handleHealth);
    return () => {
      ws.unsubscribe('health_check', handleHealth);
      ws.unsubscribe('agent_health', handleHealth);
    };
  }, [ws]);

  const healthyAgents = agents.filter(a => a.status === 'healthy');
  const unhealthyAgents = agents.filter(a => a.status === 'unhealthy');
  const otherAgents = agents.filter(a => a.status !== 'healthy' && a.status !== 'unhealthy');

  const totalMessages = agents.reduce((sum, a) => sum + (a.messagesProcessed || 0), 0);
  const totalErrors = agents.reduce((sum, a) => sum + (a.errors || 0), 0);
  const totalPnL = agents.reduce((sum, a) => sum + (a.pnlToday || 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Trading Agents</h1>
        <div className="flex gap-4 text-sm">
          <span className="text-profit">Healthy: {healthyAgents.length}</span>
          <span className="text-loss">Unhealthy: {unhealthyAgents.length}</span>
          <span className="text-slate-400">Other: {otherAgents.length}</span>
        </div>
      </div>

      {/* Agent Metrics Summary */}
      {agents.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <Activity size={16} />
              <span className="text-sm">Total Messages</span>
            </div>
            <p className="text-2xl font-bold text-white">{totalMessages.toLocaleString()}</p>
          </div>
          <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <AlertTriangle size={16} />
              <span className="text-sm">Total Errors</span>
            </div>
            <p className={`text-2xl font-bold ${totalErrors > 0 ? 'text-loss' : 'text-profit'}`}>
              {totalErrors}
            </p>
          </div>
          <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <TrendingUp size={16} />
              <span className="text-sm">Daily PnL</span>
            </div>
            <p className={`text-2xl font-bold ${totalPnL >= 0 ? 'text-profit' : 'text-loss'}`}>
              {totalPnL >= 0 ? '+' : ''}{totalPnL.toFixed(4)} SOL
            </p>
          </div>
          <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
            <div className="flex items-center gap-2 text-slate-400 mb-1">
              <Clock size={16} />
              <span className="text-sm">Avg Response</span>
            </div>
            <p className="text-2xl font-bold text-white">
              {agents.some(a => a.avgResponseTime) 
                ? `${Math.round(agents.reduce((sum, a) => sum + (a.avgResponseTime || 0), 0) / agents.filter(a => a.avgResponseTime).length)}ms`
                : 'N/A'}
            </p>
          </div>
        </div>
      )}

      {healthyAgents.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 text-slate-300 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-profit" />
            Healthy Agents
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {healthyAgents.map(agent => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        </section>
      )}

      {unhealthyAgents.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 text-slate-300 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-loss" />
            Unhealthy Agents
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {unhealthyAgents.map(agent => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        </section>
      )}

      {otherAgents.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 text-slate-300">Other Agents</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {otherAgents.map(agent => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        </section>
      )}

      {agents.length === 0 && (
        <div className="text-center py-16 text-slate-500">
          <p className="text-lg">No agents connected</p>
          <p className="text-sm mt-2">Agent health updates will appear here</p>
        </div>
      )}
    </div>
  );
}