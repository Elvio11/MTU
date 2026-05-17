import React from 'react';
import { GlassCard } from './GlassCard';
import { Cpu, Activity, AlertTriangle, Clock } from 'lucide-react';

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

interface AgentCardProps {
  agent: Agent;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const statusColor = 
    agent.status === 'healthy' ? 'text-profit' : 
    agent.status === 'unhealthy' ? 'text-loss' : 
    agent.status === 'starting' ? 'text-mtus-accent' : 'text-muted';

  return (
    <GlassCard 
      title={agent.name} 
      subtitle={`ID: ${agent.id}`} 
      icon={Cpu}
      className="h-full"
    >
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <span className="text-[10px] font-bold text-muted uppercase tracking-widest">Status</span>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${agent.status === 'healthy' ? 'bg-profit' : 'bg-loss'} animate-pulse`} />
            <span className={`text-xs font-bold uppercase ${statusColor}`}>{agent.status}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 pt-2">
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-muted">
              <Activity size={12} />
              <span className="text-[10px] font-bold uppercase">Messages</span>
            </div>
            <p className="text-sm font-bold text-white">{agent.messagesProcessed || 0}</p>
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-1 text-muted">
              <AlertTriangle size={12} />
              <span className="text-[10px] font-bold uppercase">Errors</span>
            </div>
            <p className={`text-sm font-bold ${agent.errors ? 'text-loss' : 'text-profit'}`}>{agent.errors || 0}</p>
          </div>
        </div>

        <div className="pt-2 border-t border-white/5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1 text-muted">
              <Clock size={12} />
              <span className="text-[10px] font-bold uppercase">Heartbeat</span>
            </div>
            <span className="text-[10px] font-mono text-white/60">{agent.lastHeartbeat}</span>
          </div>
        </div>
      </div>
    </GlassCard>
  );
};

export default AgentCard;
