interface AgentCardProps {
  agent: {
    id: string;
    name: string;
    status: 'healthy' | 'unhealthy' | 'starting' | 'paused';
    lastHeartbeat: string;
    tradesToday?: number;
    pnlToday?: number;
  };
}

export default function AgentCard({ agent }: AgentCardProps) {
  const statusConfig: Record<string, { color: string; text: string }> = {
    healthy: { color: 'bg-profit', text: 'Healthy' },
    unhealthy: { color: 'bg-loss', text: 'Unhealthy' },
    starting: { color: 'bg-warning', text: 'Starting' },
    paused: { color: 'bg-muted', text: 'Paused' },
  };

  const config = statusConfig[agent.status] || { color: 'bg-muted', text: 'Unknown' };

  return (
    <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-semibold text-white">{agent.name}</h3>
          <p className="text-xs text-slate-400">{agent.id}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full ${config.color}`} />
          <span className="text-xs text-slate-400">{config.text}</span>
        </div>
      </div>
      
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-slate-400">Last Heartbeat</span>
          <span className="text-white">{agent.lastHeartbeat}</span>
        </div>
        {agent.tradesToday !== undefined && (
          <div className="flex justify-between">
            <span className="text-slate-400">Trades Today</span>
            <span className="text-white">{agent.tradesToday}</span>
          </div>
        )}
        {agent.pnlToday !== undefined && (
          <div className="flex justify-between">
            <span className="text-slate-400">PnL Today</span>
            <span className={agent.pnlToday >= 0 ? 'text-profit' : 'text-loss'}>
              {agent.pnlToday >= 0 ? '+' : ''}{agent.pnlToday.toFixed(4)} SOL
            </span>
          </div>
        )}
      </div>
    </div>
  );
}