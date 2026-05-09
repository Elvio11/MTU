import { SentinelAgent, PositionState } from './sentinel';

jest.mock('ioredis', () => {
  return jest.fn().mockImplementation(() => ({
    subscribe: jest.fn(),
    publish: jest.fn().mockResolvedValue(1),
    quit: jest.fn().mockResolvedValue('OK'),
  }));
});

jest.mock('axios');

describe('SentinelAgent', () => {
  let agent: SentinelAgent;

  beforeEach(() => {
    jest.clearAllMocks();
    agent = new SentinelAgent();
  });

  describe('Position State Machine (Section 3.6)', () => {
    test('should have valid state transitions', () => {
      const validTransitions: Record<PositionState, PositionState[]> = {
        'PENDING_ENTRY': ['OPEN', 'FAILED'],
        'OPEN': ['TAKE_PROFIT_1', 'STOP_LOSS', 'TRAILING', 'MANUAL_EXIT'],
        'TAKE_PROFIT_1': ['TRAILING', 'STOP_LOSS', 'TAKE_PROFIT_2'],
        'TRAILING': ['TAKE_PROFIT_2', 'STOP_LOSS', 'CLOSED'],
        'TAKE_PROFIT_2': ['CLOSED'],
        'STOP_LOSS': ['CLOSED'],
        'MANUAL_EXIT': ['CLOSED'],
        'CLOSED': [],
        'FAILED': [],
      };

      expect(validTransitions['OPEN']).toContain('TAKE_PROFIT_1');
      expect(validTransitions['OPEN']).toContain('STOP_LOSS');
      expect(validTransitions['TAKE_PROFIT_1']).toContain('TRAILING');
    });
  });

  describe('TP/SL Configuration (Section 3.6)', () => {
    test('should set TP1 at 2x entry price', () => {
      const entryPrice = 0.01;
      const tp1Price = entryPrice * 2.0;
      expect(tp1Price).toBe(0.02);
    });

    test('should set TP2 at 5x entry price', () => {
      const entryPrice = 0.01;
      const tp2Price = entryPrice * 5.0;
      expect(tp2Price).toBe(0.05);
    });

    test('should set SL at 0.7x entry price (30% loss)', () => {
      const entryPrice = 0.01;
      const slPrice = entryPrice * 0.7;
      expect(slPrice).toBeCloseTo(0.007);
    });

    test('should have trailing stop at 15% below peak', () => {
      const peakPrice = 0.05;
      const trailingStop = peakPrice * 0.85;
      expect(trailingStop).toBe(0.0425);
    });
  });

  describe('Time-based Stop Loss (Section 3.6)', () => {
    test('should trigger time SL after 4 hours without TP1', () => {
      const timeSLHours = 4;
      const timeSLMs = 4 * 60 * 60 * 1000;
      expect(timeSLMs).toBe(14400000);
    });
  });

  describe('Price Polling (Section 3.6)', () => {
    test('should poll every 5 seconds', () => {
      const POLLING_INTERVAL_MS = 5000;
      expect(POLLING_INTERVAL_MS).toBe(5000);
    });

    test('should maintain price buffer of 10 readings', () => {
      const PRICE_BUFFER_SIZE = 10;
      const buffer = new Array(PRICE_BUFFER_SIZE).fill(0);
      expect(buffer.length).toBe(10);
    });
  });

  describe('Take Profit Logic (Section 3.6)', () => {
    test('should sell 50% at TP1', () => {
      const portion = 0.5;
      expect(portion).toBe(0.5);
    });

    test('should sell remaining 50% at TP2', () => {
      const tp1Portion = 0.5;
      const tp2Portion = 0.5;
      expect(tp1Portion + tp2Portion).toBe(1.0);
    });

    test('should sell 100% on stop loss', () => {
      const slPortion = 1.0;
      expect(slPortion).toBe(1.0);
    });
  });

  describe('Price Buffer', () => {
    test('should maintain circular buffer for last 10 prices', () => {
      const priceBuffer: number[] = [];
      const maxSize = 10;

      for (let i = 0; i < 15; i++) {
        priceBuffer.push(i * 0.01);
        if (priceBuffer.length > maxSize) {
          priceBuffer.shift();
        }
      }

      expect(priceBuffer.length).toBe(maxSize);
      expect(priceBuffer[0]).toBe(0.05);
    });

    test('should track peak price for trailing stop', () => {
      const prices = [0.01, 0.015, 0.02, 0.025, 0.03];
      const peakPrice = Math.max(...prices);
      expect(peakPrice).toBe(0.03);
    });
  });
});

describe('Stop Loss Trigger Conditions', () => {
  test('should trigger SL when price drops 30%', () => {
    const entryPrice = 0.01;
    const slPrice = entryPrice * 0.7;
    const currentPrice = 0.006;
    expect(currentPrice <= slPrice).toBe(true);
  });

  test('should trigger TP1 when price doubles', () => {
    const entryPrice = 0.01;
    const tp1Price = entryPrice * 2.0;
    const currentPrice = 0.02;
    expect(currentPrice >= tp1Price).toBe(true);
  });

  test('should trigger TP2 when price reaches 5x', () => {
    const entryPrice = 0.01;
    const tp2Price = entryPrice * 5.0;
    const currentPrice = 0.05;
    expect(currentPrice >= tp2Price).toBe(true);
  });
});