'use client';

import { useEffect, useState, useMemo } from 'react';
import { useWebSocket } from '@/lib/websocket';
import { 
  TrendingUp, 
  Activity, 
  Shield, 
  Zap, 
  AlertTriangle, 
  CheckCircle2, 
  Play, 
  Square,
  BarChart3,
  List,
  Cpu
} from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from 'recharts';

interface SystemStats {
  api: Record<string, any>;
  metrics: {
    total_pnl: number;
    open_positions: number;
    win_rate: number;
    current_position_size: number;
  };
  timestamp: number;
}

interface Position {
  position_id: string;
  mint: string;
  symbol: string;
  entry_price_sol: number;
  current_price_sol: number;
  pnl_sol: number;
  pnl_pct: number;
  state: string;
  quantity: number;
}

interface AgentStatus {
  agent_id: string;
  status: 'healthy' | 'unhealthy';
  last_update: string;
}

export default function TerminalPage() {
  const ws = useWebSocket();
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [agents, setAgents] = useState<Record<string, AgentStatus>>({});
  const [logs, setLogs] = useState<{msg: string, type: string, time: string}[]>([]);

  useEffect(() => {
    if (!ws) return;

    const handleStats = (payload: any) => setStats(payload);
    const handleHealth = (payload: any) => {
      setAgents(prev => ({
        ...prev,
        [payload.agent_id]: {
          agent_id: payload.agent_id,
          status: payload.payload?.status === 'healthy' ? 'healthy' : 'unhealthy',
          last_update: new Date().toLocaleTimeString()
        }
      }));
    };
    
    const handlePrice = (payload: any) => {
      setPositions(prev => prev.map(p => 
        p.mint === payload.mint 
          ? { 
              ...p, 
              current_price_sol: payload.price_sol,
              pnl_sol: (payload.price_sol - p.entry_price_sol) * p.quantity,
              pnl_pct: ((payload.price_sol - p.entry_price_sol) / p.entry_price_sol) * 100
            }
          : p
      ));
    };

    const handleOpen = (payload: any) => {
      setPositions(prev => [...prev, {
        position_id: payload.position_id,
        mint: payload.mint,
        symbol: payload.symbol || 'TKN',
        entry_price_sol: payload.entry_price_sol,
        current_price_sol: payload.entry_price_sol,
        pnl_sol: 0,
        pnl_pct: 0,
        state: 'OPEN',
        quantity: payload.quantity || 0
      }]);
      addLog(`Opened position: ${payload.symbol || payload.mint}`, 'success');
    };

    const handleClose = (payload: any) => {
      setPositions(prev => prev.filter(p => p.position_id !== payload.position_id));
      addLog(`Closed position: ${payload.position_id} | PnL: ${payload.realised_pnl_sol?.toFixed(4)}`, payload.realised_pnl_sol > 0 ? 'success' : 'error');
    };

    const handleAlert = (payload: any) => {
      addLog(payload.message, payload.level === 'CRITICAL' ? 'critical' : 'warning');
    };

    const addLog = (msg: string, type: string) => {
      setLogs(prev => [{ msg, type, time: new Date().toLocaleTimeString() }, ...prev].slice(0, 50));
    };

    ws.subscribe('system_stats', handleStats);
    ws.subscribe('health_check', handleHealth);
    ws.subscribe('price_updated', handlePrice);
    ws.subscribe('position_opened', handleOpen);
    ws.subscribe('position_closed', handleClose);
    ws.subscribe('system_alert', handleAlert);

    return () => {
      ws.unsubscribe('system_stats', handleStats);
      ws.unsubscribe('health_check', handleHealth);
      ws.unsubscribe('price_updated', handlePrice);
      ws.unsubscribe('position_opened', handleOpen);
      ws.unsubscribe('position_closed', handleClose);
      ws.unsubscribe('system_alert', handleAlert);
    };
  }, [ws]);

  const statsList = [
    { label: 'Total PnL', value: `${stats?.metrics.total_pnl.toFixed(4)} SOL`, icon: TrendingUp, color: (stats?.metrics.total_pnl || 0) >= 0 ? 'text-profit' : 'text-loss' },
    { label: 'Open Positions', value: stats?.metrics.open_positions || 0, icon: List, color: 'text-mtus-accent' },
    { label: 'Win Rate', value: `${stats?.metrics.win_rate.toFixed(1)}%`, icon: BarChart3, color: 'text-mtus-secondary' },
    { label: 'Agent Health', value: Object.values(agents).filter(a => a.status === 'healthy').length, icon: Shield, color: 'text-profit' },
  ];

  return (
    <div className="max-w-[1600px] mx-auto space-y-6 pb-12">
      {/* Top Header Section */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading text-white tracking-wider">TERMINAL</h1>
          <p className="text-muted text-sm flex items-center gap-2 mt-1">
            <span className={`w-2 h-2 rounded-full ${ws?.connected ? 'bg-profit animate-pulse' : 'bg-loss'}`} />
            {ws?.connected ? 'SYSTEM ONLINE' : 'CONNECTION LOST'}
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          <button 
            className="px-4 py-2 bg-red-500/10 border border-red-500/50 text-red-500 rounded-lg text-xs font-bold hover:bg-red-500/20 transition-all cursor-pointer flex items-center gap-2"
            onClick={() => ws?.send({type: 'command', action: 'killswitch'})}
          >
            <Zap size={14} /> EMERGENCY KILLSWITCH
          </button>
        </div>
      </header>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Stats & Positions (8/12) */}
        <div className="lg:col-span-8 space-y-6">
          
          {/* Stats Bar */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statsList.map((stat, i) => (
              <div key={i} className="bg-mtus-card backdrop-blur-md border border-white/10 p-4 rounded-2xl">
                <div className="flex items-center justify-between mb-2">
                  <stat.icon className="text-muted" size={18} />
                  <span className="text-[10px] font-bold text-muted uppercase tracking-widest">{stat.label}</span>
                </div>
                <div className={`text-xl font-bold ${stat.color}`}>{stat.value}</div>
              </div>
            ))}
          </div>

          {/* Main Chart Area */}
          <div className="bg-mtus-card backdrop-blur-md border border-white/10 rounded-2xl p-6 h-[400px]">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-sm font-bold font-heading text-muted uppercase">Market Performance</h3>
              <div className="flex gap-2">
                <span className="text-xs px-2 py-1 bg-white/5 rounded-md text-white/60">LIVE FEED</span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={logs.slice(0, 20).reverse().map((_, i) => ({name: i, pnl: Math.random() * 10}))}>
                <defs>
                  <linearGradient id="colorPnL" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="name" hide />
                <YAxis hide />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', border: '1px solid rgba(255,255,255,0.1)' }}
                  itemStyle={{ color: '#f59e0b' }}
                />
                <Area type="monotone" dataKey="pnl" stroke="#f59e0b" fillOpacity={1} fill="url(#colorPnL)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Positions Table */}
          <div className="bg-mtus-card backdrop-blur-md border border-white/10 rounded-2xl overflow-hidden">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h3 className="text-sm font-bold font-heading text-muted uppercase">Active Positions</h3>
              <span className="text-xs text-muted font-bold">{positions.length} RUNNING</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-[10px] text-muted font-bold uppercase border-b border-white/5">
                    <th className="px-6 py-4">Asset</th>
                    <th className="px-6 py-4">Entry</th>
                    <th className="px-6 py-4">Current</th>
                    <th className="px-6 py-4">PnL (SOL)</th>
                    <th className="px-6 py-4">Return %</th>
                    <th className="px-6 py-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {positions.map((pos) => (
                    <tr key={pos.position_id} className="hover:bg-white/5 transition-colors group">
                      <td className="px-6 py-4">
                        <div className="flex flex-col">
                          <span className="text-sm font-bold text-white">{pos.symbol}</span>
                          <span className="text-[10px] text-muted font-mono">{pos.mint.slice(0, 8)}...</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm font-mono text-muted">{pos.entry_price_sol.toFixed(6)}</td>
                      <td className="px-6 py-4 text-sm font-mono text-white">{pos.current_price_sol.toFixed(6)}</td>
                      <td className={`px-6 py-4 text-sm font-bold ${pos.pnl_sol >= 0 ? 'text-profit' : 'text-loss'}`}>
                        {pos.pnl_sol >= 0 ? '+' : ''}{pos.pnl_sol.toFixed(4)}
                      </td>
                      <td className={`px-6 py-4 text-sm font-bold ${pos.pnl_pct >= 0 ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'} rounded-md inline-block my-4 mx-6`}>
                        {pos.pnl_pct.toFixed(2)}%
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button className="p-2 hover:bg-white/10 rounded-lg text-muted hover:text-white transition-all cursor-pointer">
                          <Zap size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {positions.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-muted italic text-sm">
                        No active market exposure detected.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: Agents, Controls & Logs (4/12) */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* System Control Panel */}
          <div className="bg-mtus-card backdrop-blur-md border border-white/10 rounded-2xl p-6">
            <h3 className="text-sm font-bold font-heading text-muted uppercase mb-4">Control System</h3>
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-muted uppercase tracking-widest">Position Size (SOL)</label>
                <div className="flex gap-2">
                  <input 
                    type="number" 
                    step="0.01" 
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-mtus-accent/50"
                    placeholder="0.1"
                    defaultValue={stats?.metrics.current_position_size}
                    id="pos_size_input"
                  />
                  <button 
                    className="px-3 py-2 bg-mtus-accent text-white rounded-lg text-xs font-bold hover:opacity-80"
                    onClick={() => {
                      const val = (document.getElementById('pos_size_input') as HTMLInputElement).value;
                      ws?.send({type: 'command', action: 'update_config', params: {position_size: parseFloat(val)}});
                    }}
                  >
                    SET
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-muted uppercase tracking-widest">Take Profit 1</label>
                  <input type="text" className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" placeholder="2.0x" />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-muted uppercase tracking-widest">Stop Loss</label>
                  <input type="text" className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" placeholder="0.5x" />
                </div>
              </div>

              <button 
                className="w-full py-3 bg-white/5 border border-white/10 text-white rounded-xl text-xs font-bold hover:bg-white/10 transition-all flex items-center justify-center gap-2"
                onClick={() => ws?.send({type: 'command', action: 'trigger_maintenance'})}
              >
                <Shield size={14} className="text-mtus-accent" /> TRIGGER MAINTENANCE
              </button>
            </div>
          </div>

          {/* Agent Grid */}
          <div className="bg-mtus-card backdrop-blur-md border border-white/10 rounded-2xl p-4">
            <h3 className="text-sm font-bold font-heading text-muted uppercase mb-4 px-2">Agent Status</h3>
            <div className="grid grid-cols-1 gap-3">
              {Object.values(agents).map(agent => (
                <div key={agent.agent_id} className="flex items-center justify-between p-3 bg-white/5 rounded-xl border border-white/5">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${agent.status === 'healthy' ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'}`}>
                      <Cpu size={16} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-white uppercase">{agent.agent_id}</div>
                      <div className="text-[10px] text-muted tracking-tight">LAST HEARTBEAT: {agent.last_update}</div>
                    </div>
                  </div>
                  <div className={`w-2 h-2 rounded-full ${agent.status === 'healthy' ? 'bg-profit shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-loss'}`} />
                </div>
              ))}
              {Object.keys(agents).length === 0 && (
                <div className="text-center py-6 text-[10px] text-muted font-bold uppercase">
                  Initializing agents...
                </div>
              )}
            </div>
          </div>

          {/* Activity Log */}
          <div className="bg-mtus-card backdrop-blur-md border border-white/10 rounded-2xl flex flex-col h-[600px]">
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h3 className="text-sm font-bold font-heading text-muted uppercase">Terminal Logs</h3>
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-profit animate-pulse" />
              </div>
            </div>
            <div className="flex-1 overflow-auto p-4 space-y-4 font-mono">
              {logs.map((log, i) => (
                <div key={i} className="text-[11px] leading-relaxed animate-in fade-in slide-in-from-top-2 duration-300">
                  <span className="text-muted mr-2">[{log.time}]</span>
                  <span className={`
                    ${log.type === 'success' ? 'text-profit' : ''}
                    ${log.type === 'error' ? 'text-loss' : ''}
                    ${log.type === 'warning' ? 'text-warning' : ''}
                    ${log.type === 'critical' ? 'text-red-500 font-bold underline' : ''}
                    ${log.type === 'info' ? 'text-mtus-secondary' : 'text-slate-200'}
                  `}>
                    {log.msg}
                  </span>
                </div>
              ))}
              {logs.length === 0 && (
                <div className="text-center text-muted text-[10px] uppercase font-bold mt-20">
                  Awaiting system events...
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}