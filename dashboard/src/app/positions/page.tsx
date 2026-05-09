'use client';

import { useEffect, useState } from 'react';
import { useWebSocket } from '@/lib/websocket';
import PositionCard from '@/components/PositionCard';

interface Position {
  positionId: string;
  mint: string;
  symbol?: string;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  pnlPct: number;
  state: string;
  quantity: number;
}

interface PositionOpenedPayload {
  position_id: string;
  mint: string;
  symbol?: string;
  entry_price_sol: number;
  quantity?: number;
}

interface PositionClosedPayload {
  position_id: string;
}

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const ws = useWebSocket();

  useEffect(() => {
    if (!ws) return;

    const handleOpened = (payload: unknown) => {
      const data = payload as PositionOpenedPayload;
      setPositions(prev => [...prev, {
        positionId: data.position_id,
        mint: data.mint,
        symbol: data.symbol || 'TOKEN',
        entryPrice: data.entry_price_sol,
        currentPrice: data.entry_price_sol,
        pnl: 0,
        pnlPct: 0,
        state: 'OPEN',
        quantity: data.quantity || 0
      }]);
    };

    const handleClosed = (payload: unknown) => {
      const data = payload as PositionClosedPayload;
      setPositions(prev => prev.filter(p => p.positionId !== data.position_id));
    };

    ws.subscribe('position_opened', handleOpened);
    ws.subscribe('position_closed', handleClosed);

    return () => {
      ws.unsubscribe('position_opened', handleOpened);
      ws.unsubscribe('position_closed', handleClosed);
    };
  }, [ws]);

  const openPositions = positions.filter(p => p.state === 'OPEN');
  const closedPositions = positions.filter(p => p.state !== 'OPEN');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Positions</h1>
        <div className="flex gap-4 text-sm">
          <span className="text-slate-400">Open: <span className="text-white font-medium">{openPositions.length}</span></span>
          <span className="text-slate-400">Closed: <span className="text-white font-medium">{closedPositions.length}</span></span>
        </div>
      </div>

      {openPositions.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 text-slate-300">Open Positions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {openPositions.map(pos => (
              <PositionCard key={pos.positionId} position={pos} />
            ))}
          </div>
        </section>
      )}

      {closedPositions.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 text-slate-300">Closed Positions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {closedPositions.map(pos => (
              <PositionCard key={pos.positionId} position={pos} />
            ))}
          </div>
        </section>
      )}

      {positions.length === 0 && (
        <div className="text-center py-16 text-slate-500">
          <p className="text-lg">No positions yet</p>
          <p className="text-sm mt-2">Open positions will appear here when trades are executed</p>
        </div>
      )}
    </div>
  );
}