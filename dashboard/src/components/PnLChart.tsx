'use client';

import { useEffect, useState } from 'react';
import { useWebSocket } from '@/lib/websocket';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

interface DataPoint {
  time: string;
  pnl: number;
}

interface PnlUpdatePayload {
  time?: string;
  pnl?: number;
}

export default function PnLChart() {
  const [data, setData] = useState<DataPoint[]>(() => {
    const now = new Date();
    const points: DataPoint[] = [];
    for (let i = 23; i >= 0; i--) {
      const time = new Date(now.getTime() - i * 60 * 60 * 1000);
      points.push({
        time: time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        pnl: 0,
      });
    }
    return points;
  });
  const ws = useWebSocket();

  useEffect(() => {
    if (!ws) return;

    const handler = (payload: unknown) => {
      const pnlData = payload as PnlUpdatePayload;
      if (pnlData.time && pnlData.pnl !== undefined) {
        setData(prev => [...prev.slice(-23), { time: pnlData.time, pnl: pnlData.pnl } as DataPoint]);
      }
    };

    ws.subscribe('pnl_update', handler);
    return () => ws.unsubscribe('pnl_update', handler);
  }, [ws]);

  return (
    <div className="bg-mtus-card p-4 rounded-xl border border-slate-700">
      <ResponsiveContainer width="100%" height={250}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis 
            dataKey="time" 
            stroke="#64748b" 
            fontSize={12}
            tickLine={false}
          />
          <YAxis 
            stroke="#64748b" 
            fontSize={12}
            tickLine={false}
            tickFormatter={(value) => `${value.toFixed(1)}`}
          />
          <Tooltip
            contentStyle={{ 
              backgroundColor: '#1e293b', 
              border: '1px solid #334155', 
              borderRadius: '8px',
              color: '#fff'
            }}
            labelStyle={{ color: '#94a3b8' }}
          />
          <Area
            type="monotone"
            dataKey="pnl"
            stroke="#22c55e"
            strokeWidth={2}
            fill="url(#pnlGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}