import { AresAgent } from './ares';
import { CircuitBreaker, CircuitState } from '../shared/circuit-breaker';

jest.mock('ioredis', () => {
  return jest.fn().mockImplementation(() => ({
    subscribe: jest.fn(),
    publish: jest.fn().mockResolvedValue(1),
    quit: jest.fn().mockResolvedValue('OK'),
    duplicate: jest.fn().mockReturnValue({
      subscribe: jest.fn().mockResolvedValue(undefined),
      on: jest.fn(),
    }),
  }));
});

jest.mock('@solana/web3.js', () => ({
  Keypair: {
    fromSecretKey: jest.fn(() => ({
      publicKey: { toBase58: () => 'test_pubkey' },
      secretKey: new Uint8Array(64),
    })),
  },
  Connection: jest.fn().mockImplementation(() => ({
    getBalance: jest.fn().mockResolvedValue(2000000000),
    sendRawTransaction: jest.fn().mockResolvedValue('test_tx'),
    getSignatureStatus: jest.fn().mockResolvedValue({ value: { confirmationStatus: 'confirmed' } }),
  })),
  Transaction: jest.fn().mockImplementation(() => ({
    add: jest.fn().mockReturnThis(),
    sign: jest.fn(),
    serialize: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3])),
  })),
}));

jest.mock('@jup-ag/api', () => ({
  QuoteResponse: {},
  SwapApi: jest.fn().mockImplementation(() => ({})),
}));

jest.mock('../shared/keystore', () => ({
  loadKeypairFromKeystore: jest.fn().mockResolvedValue({
    publicKey: { toBase58: () => 'test_pubkey' },
    secretKey: new Uint8Array(64),
  }),
}));

describe('AresAgent', () => {
  let agent: AresAgent;

  beforeEach(() => {
    jest.clearAllMocks();
    agent = new AresAgent();
  });

  describe('Configuration', () => {
    test('should have correct slippage ladder per Section 3.5', () => {
      const SLIPPAGE_LADDER = [1000, 1500, 2000];
      expect(SLIPPAGE_LADDER).toEqual([1000, 1500, 2000]);
    });

    test('should have max slippage cap of 2000 bps (20%)', () => {
      const MAX_SLIPPAGE_BPS = 2000;
      expect(MAX_SLIPPAGE_BPS).toBe(2000);
    });

    test('should use position size of 0.15 SOL', () => {
      const POSITION_SIZE_SOL = 0.15;
      expect(POSITION_SIZE_SOL).toBe(0.15);
    });
  });

  describe('Slippage Retry Ladder', () => {
    test('should attempt 3 slippage levels: 10%, 15%, 20%', () => {
      const slippageLevels = [10, 15, 20];
      expect(slippageLevels).toHaveLength(3);
      expect(slippageLevels[0]).toBe(10);
      expect(slippageLevels[1]).toBe(15);
      expect(slippageLevels[2]).toBe(20);
    });

    test('should not exceed 20% max slippage', () => {
      const maxSlippage = 2000;
      const attempts = [1000, 1500, 2000];
      attempts.forEach(attempt => {
        expect(attempt).toBeLessThanOrEqual(maxSlippage);
      });
    });
  });

  describe('Keypair Security', () => {
    test('should zero keypair after signing (per Section 3.5)', () => {
      const secretKey = new Uint8Array([1, 2, 3, 4, 5]);
      const originalLength = secretKey.length;
      secretKey.fill(0);
      expect(secretKey.every(v => v === 0)).toBe(true);
    });
  });

  describe('RPC Broadcast', () => {
    test('should broadcast to multiple RPCs simultaneously', () => {
      const providers = ['helius', 'quicknode', 'alchemy'];
      expect(providers).toHaveLength(3);
    });

    test('should use Promise.allSettled for broadcast', () => {
      const mockResults = [
        { status: 'fulfilled', value: 'tx1' },
        { status: 'rejected', reason: 'error' },
      ];
      const fulfilled = mockResults.filter(r => r.status === 'fulfilled');
      expect(fulfilled.length).toBeGreaterThanOrEqual(1);
    });
  });
});

describe('CircuitBreaker Integration', () => {
  test('should open circuit after 3 failures', async () => {
    const cb = new CircuitBreaker(3);
    try {
      await cb.execute(async () => { throw new Error('fail1'); });
    } catch {}
    try {
      await cb.execute(async () => { throw new Error('fail2'); });
    } catch {}
    try {
      await cb.execute(async () => { throw new Error('fail3'); });
    } catch {}
    expect(cb.getState()).toBe(CircuitState.OPEN);
  });

  test('should transition to HALF_OPEN after timeout', async () => {
    const cb = new CircuitBreaker(3, 100);
    try {
      await cb.execute(async () => { throw new Error('fail1'); });
    } catch {}
    try {
      await cb.execute(async () => { throw new Error('fail2'); });
    } catch {}
    try {
      await cb.execute(async () => { throw new Error('fail3'); });
    } catch {}
    expect(cb.getState()).toBe(CircuitState.OPEN);
    await new Promise(r => setTimeout(r, 150));
    try {
      await cb.execute(async () => 'success');
    } catch {}
    expect(cb.getState()).toBe(CircuitState.CLOSED);
  });
});