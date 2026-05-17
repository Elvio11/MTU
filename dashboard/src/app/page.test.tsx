import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import React from 'react';

const mockSubscribe = vi.fn();
const mockUnsubscribe = vi.fn();
const mockSend = vi.fn();
let mockConnected = false;
const mockUseWebSocket = vi.fn(() => ({
  subscribe: mockSubscribe,
  unsubscribe: mockUnsubscribe,
  send: mockSend,
  connected: mockConnected,
  reconnecting: false,
  lastMessage: null,
  setAuthToken: vi.fn(),
}));

vi.mock('@/lib/websocket', () => ({
  useWebSocket: () => mockUseWebSocket(),
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  AreaChart: ({ children }: any) => <div>{children}</div>,
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}));

let TerminalPage: any;

beforeEach(async () => {
  vi.clearAllMocks();
  mockUseWebSocket.mockImplementation(() => ({
    subscribe: mockSubscribe,
    unsubscribe: mockUnsubscribe,
    send: mockSend,
    connected: mockConnected,
    reconnecting: false,
    lastMessage: null,
    setAuthToken: vi.fn(),
  }));
  mockConnected = false;
  TerminalPage = (await import('./page')).default;
});

describe('TerminalPage', () => {
  it('shows TERMINAL heading', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('TERMINAL')).toBeInTheDocument();
  });

  it('shows CONNECTION LOST when ws not connected', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('CONNECTION LOST')).toBeInTheDocument();
  });

  it('shows SYSTEM ONLINE when ws connected', () => {
    mockConnected = true;
    mockUseWebSocket.mockReturnValue({
      subscribe: mockSubscribe, unsubscribe: mockUnsubscribe, send: mockSend,
      connected: true, reconnecting: false, lastMessage: null, setAuthToken: vi.fn(),
    });
    render(React.createElement(TerminalPage));
    expect(screen.getByText('SYSTEM ONLINE')).toBeInTheDocument();
  });

  it('has EMERGENCY KILLSWITCH button', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('EMERGENCY KILLSWITCH')).toBeInTheDocument();
  });

  it('has position size input and SET button', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('SET')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('0.1')).toBeInTheDocument();
  });

  it('shows Awaiting system events when no logs', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('Awaiting system events...')).toBeInTheDocument();
  });

  it('shows Initializing agents when no agents', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('Initializing agents...')).toBeInTheDocument();
  });

  it('shows No active market exposure when no positions', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('No active market exposure detected.')).toBeInTheDocument();
  });

  it('subscribes to WebSocket events on mount', () => {
    render(React.createElement(TerminalPage));
    expect(mockSubscribe).toHaveBeenCalledWith('system_stats', expect.any(Function));
    expect(mockSubscribe).toHaveBeenCalledWith('health_check', expect.any(Function));
    expect(mockSubscribe).toHaveBeenCalledWith('price_updated', expect.any(Function));
    expect(mockSubscribe).toHaveBeenCalledWith('position_opened', expect.any(Function));
    expect(mockSubscribe).toHaveBeenCalledWith('position_closed', expect.any(Function));
    expect(mockSubscribe).toHaveBeenCalledWith('system_alert', expect.any(Function));
  });

  it('unsubscribes from WebSocket events on unmount', () => {
    const { unmount } = render(React.createElement(TerminalPage));
    unmount();
    expect(mockUnsubscribe).toHaveBeenCalledWith('system_stats', expect.any(Function));
    expect(mockUnsubscribe).toHaveBeenCalledWith('system_alert', expect.any(Function));
  });

  it('renders Stats cards with zeros initially', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('Total PnL')).toBeInTheDocument();
    expect(screen.getByText('Open Positions')).toBeInTheDocument();
    expect(screen.getByText('Win Rate')).toBeInTheDocument();
    expect(screen.getByText('Agent Health')).toBeInTheDocument();
  });

  it('receives system_stats and updates display', () => {
    let statsHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'system_stats') statsHandler = handler;
    });
    render(React.createElement(TerminalPage));
    act(() => {
      statsHandler({ metrics: { total_pnl: 42.5, open_positions: 3, win_rate: 66.7, current_position_size: 0.5 } });
    });
    expect(screen.getByText('42.5000 SOL')).toBeInTheDocument();
    expect(screen.getByText('66.7%')).toBeInTheDocument();
  });

  it('receives health_check and updates agents', () => {
    let healthHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'health_check') healthHandler = handler;
    });
    render(React.createElement(TerminalPage));
    act(() => {
      healthHandler({ agent_id: 'ares', payload: { status: 'healthy' } });
    });
    expect(screen.getByText('ares')).toBeInTheDocument();
  });

  it('does not subscribe when ws is null', () => {
    mockUseWebSocket.mockImplementationOnce(() => null as any);
    render(React.createElement(TerminalPage));
    expect(mockSubscribe).not.toHaveBeenCalled();
  });

  it('receives position_opened and shows position in table', () => {
    let openHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
    });
    render(React.createElement(TerminalPage));
    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 150.5,
        quantity: 2,
      });
    });
    expect(screen.getByText('SOL')).toBeInTheDocument();
    expect(screen.getAllByText('150.500000')).toHaveLength(2);
    expect(screen.getByText(/Opened position: SOL/)).toBeInTheDocument();
    expect(screen.queryByText('No active market exposure detected.')).not.toBeInTheDocument();
  });

  it('receives position_opened with default symbol TKN when no symbol provided', () => {
    let openHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
    });
    render(React.createElement(TerminalPage));
    act(() => {
      openHandler({
        position_id: 'pos2',
        mint: 'UnknownMint1111111111111111111111111111111',
        entry_price_sol: 10,
        quantity: 1,
      });
    });
    expect(screen.getByText('TKN')).toBeInTheDocument();
  });

  it('receives position_closed and removes position from table', () => {
    let openHandler: Function = () => {};
    let closeHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
      if (type === 'position_closed') closeHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 150,
        quantity: 1,
      });
    });
    expect(screen.getByText('SOL')).toBeInTheDocument();

    act(() => {
      closeHandler({ position_id: 'pos1', realised_pnl_sol: 10.5 });
    });
    expect(screen.queryByText('SOL')).not.toBeInTheDocument();
    expect(screen.getByText(/Closed position: pos1 \| PnL: 10.5000/)).toBeInTheDocument();
    expect(screen.getByText('No active market exposure detected.')).toBeInTheDocument();
  });

  it('receives position_closed with negative PnL and shows error log', () => {
    let openHandler: Function = () => {};
    let closeHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
      if (type === 'position_closed') closeHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 150,
        quantity: 1,
      });
    });

    act(() => {
      closeHandler({ position_id: 'pos1', realised_pnl_sol: -5.25 });
    });
    expect(screen.getByText(/Closed position: pos1/)).toBeInTheDocument();
    expect(screen.getByText(/-5.2500/)).toBeInTheDocument();
  });

  it('receives price_updated and updates existing position PnL', () => {
    let openHandler: Function = () => {};
    let priceHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
      if (type === 'price_updated') priceHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 100,
        quantity: 1,
      });
    });

    act(() => {
      priceHandler({ mint: 'So11111111111111111111111111111111111111112', price_sol: 110 });
    });

    expect(screen.getByText('110.000000')).toBeInTheDocument();
    expect(screen.getByText('+10.0000')).toBeInTheDocument();
  });

  it('renders position with negative PnL when price drops', () => {
    let openHandler: Function = () => {};
    let priceHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
      if (type === 'price_updated') priceHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 200,
        quantity: 2,
      });
    });

    act(() => {
      priceHandler({ mint: 'So11111111111111111111111111111111111111112', price_sol: 100 });
    });

    expect(screen.getByText('-200.0000')).toBeInTheDocument();
    expect(screen.getByText('-50.00%')).toBeInTheDocument();
  });

  it('receives system_alert with WARNING level', () => {
    let alertHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'system_alert') alertHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      alertHandler({ message: 'High slippage detected', level: 'WARNING' });
    });
    expect(screen.getByText('High slippage detected')).toBeInTheDocument();
  });

  it('receives system_alert with CRITICAL level', () => {
    let alertHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'system_alert') alertHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      alertHandler({ message: 'System breach detected', level: 'CRITICAL' });
    });
    expect(screen.getByText('System breach detected')).toBeInTheDocument();
  });

  it('shows negative total PnL', () => {
    let statsHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'system_stats') statsHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      statsHandler({ metrics: { total_pnl: -5.2, open_positions: 1, win_rate: 30, current_position_size: 0.1 } });
    });
    expect(screen.getByText('-5.2000 SOL')).toBeInTheDocument();
  });

  it('shows unhealthy agent status', () => {
    let healthHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'health_check') healthHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      healthHandler({ agent_id: 'ares', payload: { status: 'unhealthy' } });
    });
    expect(screen.getByText('ares')).toBeInTheDocument();
  });

  it('shows multiple agents in the grid', () => {
    let healthHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'health_check') healthHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      healthHandler({ agent_id: 'ares', payload: { status: 'healthy' } });
      healthHandler({ agent_id: 'athena', payload: { status: 'healthy' } });
    });
    expect(screen.getByText('ares')).toBeInTheDocument();
    expect(screen.getByText('athena')).toBeInTheDocument();
  });

  it('sends killswitch command on EMERGENCY KILLSWITCH click', () => {
    render(React.createElement(TerminalPage));
    fireEvent.click(screen.getByText('EMERGENCY KILLSWITCH'));
    expect(mockSend).toHaveBeenCalledWith({ type: 'command', action: 'killswitch' });
  });

  it('sends update_config command on SET button click', () => {
    render(React.createElement(TerminalPage));
    const input = screen.getByPlaceholderText('0.1') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '2.5' } });
    fireEvent.click(screen.getByText('SET'));
    expect(mockSend).toHaveBeenCalledWith({ type: 'command', action: 'update_config', params: { position_size: 2.5 } });
  });

  it('sends trigger_maintenance command on TRIGGER MAINTENANCE click', () => {
    render(React.createElement(TerminalPage));
    fireEvent.click(screen.getByText('TRIGGER MAINTENANCE'));
    expect(mockSend).toHaveBeenCalledWith({ type: 'command', action: 'trigger_maintenance' });
  });

  it('renders log entry with timestamp format', () => {
    let openHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 100,
        quantity: 1,
      });
    });

    const logText = screen.getByText(/Opened position: SOL/);
    expect(logText).toBeInTheDocument();
    expect(logText.closest('div')?.textContent).toMatch(/\[\d{1,2}:\d{2}:\d{2} (AM|PM|am|pm)\]/);
  });

  it('updates Agent Health count in stats when agents are healthy', () => {
    let healthHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'health_check') healthHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      healthHandler({ agent_id: 'ares', payload: { status: 'healthy' } });
      healthHandler({ agent_id: 'athena', payload: { status: 'healthy' } });
      healthHandler({ agent_id: 'hermes', payload: { status: 'healthy' } });
    });
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('does not count unhealthy agents in Agent Health stats', () => {
    let healthHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'health_check') healthHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      healthHandler({ agent_id: 'ares', payload: { status: 'healthy' } });
      healthHandler({ agent_id: 'athena', payload: { status: 'unhealthy' } });
    });
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('shows LIVE FEED badge in chart area', () => {
    render(React.createElement(TerminalPage));
    expect(screen.getByText('LIVE FEED')).toBeInTheDocument();
  });

  it('shows RUNNING positions count', () => {
    let openHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 100,
        quantity: 1,
      });
      openHandler({
        position_id: 'pos2',
        mint: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
        symbol: 'USDC',
        entry_price_sol: 1,
        quantity: 100,
      });
    });
    expect(screen.getByText('2 RUNNING')).toBeInTheDocument();
  });

  it('shows LAST HEARTBEAT label for agents', () => {
    let healthHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'health_check') healthHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      healthHandler({ agent_id: 'ares', payload: { status: 'healthy' } });
    });
    expect(screen.getByText(/LAST HEARTBEAT:/)).toBeInTheDocument();
  });

  it('defaults quantity to 0 when position_opened has no quantity', () => {
    let openHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 100,
      });
    });
    expect(screen.getByText('SOL')).toBeInTheDocument();
  });

  it('ignores price_update for non-matching mint', () => {
    let openHandler: Function = () => {};
    let priceHandler: Function = () => {};
    mockSubscribe.mockImplementation((type: string, handler: Function) => {
      if (type === 'position_opened') openHandler = handler;
      if (type === 'price_updated') priceHandler = handler;
    });
    render(React.createElement(TerminalPage));

    act(() => {
      openHandler({
        position_id: 'pos1',
        mint: 'So11111111111111111111111111111111111111112',
        symbol: 'SOL',
        entry_price_sol: 100,
        quantity: 1,
      });
    });

    act(() => {
      priceHandler({ mint: 'OtherMint111111111111111111111111111111', price_sol: 999 });
    });

    expect(screen.getAllByText('100.000000')).toHaveLength(2);
  });
});
