import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import PositionCard from './PositionCard';

const basePosition = {
  positionId: 'pos-1',
  mint: '7xKXtg2CWQdLvEh1P3cAKiwAuJPqUZibK5P8f7bR1AbC',
  symbol: 'SOL',
  entryPrice: 150.5,
  currentPrice: 165.75,
  pnl: 15.25,
  pnlPct: 10.13,
  state: 'OPEN',
  quantity: 1.5,
};

describe('PositionCard', () => {
  it('renders symbol and truncated mint', () => {
    render(<PositionCard position={basePosition} />);
    expect(screen.getByText('SOL')).toBeInTheDocument();
    expect(screen.getByText('7xKXtg2CWQdL...')).toBeInTheDocument();
  });

  it('renders entry price and current price', () => {
    render(<PositionCard position={basePosition} />);
    expect(screen.getByText('150.500000 SOL')).toBeInTheDocument();
    expect(screen.getByText('165.750000 SOL')).toBeInTheDocument();
  });

  it('shows positive PnL in green with + sign', () => {
    render(<PositionCard position={basePosition} />);
    expect(screen.getByText('+15.2500 SOL')).toHaveClass('text-profit');
    expect(screen.getByText('+10.13%')).toBeInTheDocument();
  });

  it('shows negative PnL in red with - sign', () => {
    render(<PositionCard position={{ ...basePosition, pnl: -5.75, pnlPct: -3.82, currentPrice: 145.0 }} />);
    expect(screen.getByText('-5.7500 SOL')).toHaveClass('text-loss');
    expect(screen.getByText('-3.82%')).toBeInTheDocument();
  });

  it('renders Fast Sell and Details buttons', () => {
    render(<PositionCard position={basePosition} />);
    expect(screen.getByText('Fast Sell')).toBeInTheDocument();
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('defaults to UNKNOWN when no symbol', () => {
    const { symbol, ...noSymbol } = basePosition;
    render(<PositionCard position={noSymbol as any} />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
  });

  it('shows positive return styling', () => {
    render(<PositionCard position={basePosition} />);
    expect(screen.getByText('+10.13%')).toHaveClass('text-profit');
  });
});
