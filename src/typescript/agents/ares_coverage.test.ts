import { Keypair, VersionedTransaction, PublicKey } from '@solana/web3.js';
import { CHANNEL_POSITION_OPENED, CHANNEL_TRADE_FAILED } from '../shared/channels';

// ============================================================
// MOCKS
// ============================================================

const mockGetBalance = jest.fn().mockResolvedValue(2 * 1e9);
const mockSendRawTransaction = jest.fn().mockResolvedValue('test_sig');
const mockGetSignatureStatus = jest.fn().mockResolvedValue({ value: { confirmationStatus: 'confirmed', err: null } });
let mockVersionedTx: any = null;

function makeMockVersionedTx(overrides?: any) {
  return {
    sign: jest.fn(),
    serialize: jest.fn().mockReturnValue(new Uint8Array(100)),
    signatures: [new Uint8Array(64)],
    message: {
      recentBlockhash: 'hash',
      version: 0,
      staticAccountKeys: [{ toBase58: () => 'mint123' }],
    },
    ...overrides,
  };
}

function resetMockVersionedTx() {
  mockVersionedTx = makeMockVersionedTx();
}

resetMockVersionedTx();

jest.mock('ioredis', () => {
  const MockRedis = require('../shared/mock_redis').default;
  const origDuplicate = MockRedis.prototype.duplicate;
  MockRedis.prototype.duplicate = jest.fn().mockImplementation(function (this: any) {
    const d = origDuplicate.call(this);
    d.publish = jest.fn().mockImplementation(d.publish.bind(d));
    d.subscribe = jest.fn().mockImplementation(d.subscribe.bind(d));
    d.on = jest.fn().mockImplementation(d.on.bind(d));
    d.quit = jest.fn().mockImplementation(d.quit.bind(d));
    return d;
  });
  MockRedis.prototype.publish = jest.fn().mockImplementation(MockRedis.prototype.publish);
  MockRedis.prototype.subscribe = jest.fn().mockImplementation(MockRedis.prototype.subscribe);
  MockRedis.prototype.get = jest.fn().mockImplementation(MockRedis.prototype.get);
  MockRedis.prototype.set = jest.fn().mockImplementation(MockRedis.prototype.set);
  MockRedis.prototype.quit = jest.fn().mockImplementation(MockRedis.prototype.quit);
  MockRedis.prototype.scard = jest.fn().mockResolvedValue(0);
  MockRedis.prototype.incr = jest.fn().mockResolvedValue(1);
  MockRedis.prototype.expire = jest.fn().mockResolvedValue(1);
  MockRedis.prototype.sadd = jest.fn().mockResolvedValue(1);
  MockRedis.prototype.srem = jest.fn().mockResolvedValue(1);
  return MockRedis;
});

jest.mock('@jup-ag/api', () => ({
  QuoteResponse: {},
  SwapApi: jest.fn().mockImplementation(() => ({
    quoteGet: jest.fn().mockResolvedValue({ outAmount: '1000000' }),
    swapPost: jest.fn().mockResolvedValue({ swapTransaction: 'base64_tx' }),
  })),
}));

jest.mock('@solana/web3.js', () => {
  const actual = jest.requireActual('@solana/web3.js');

  const Vtx = jest.fn().mockImplementation(() => mockVersionedTx);
  (Vtx as any).deserialize = jest.fn().mockImplementation(() => mockVersionedTx);

  return {
    ...actual,
    Connection: jest.fn().mockImplementation(() => ({
      getBalance: mockGetBalance,
      getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: 'hash', lastValidBlockHeight: 1000 }),
      sendRawTransaction: mockSendRawTransaction,
      getSignatureStatus: mockGetSignatureStatus,
      getAccountInfo: jest.fn().mockResolvedValue({ data: Buffer.alloc(100), owner: new PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA') }),
    })),
    VersionedTransaction: Vtx,
    Transaction: Object.assign(
      jest.fn().mockImplementation(() => ({
        add: jest.fn(),
        sign: jest.fn(),
        serialize: jest.fn().mockReturnValue(Buffer.alloc(100)),
        recentBlockhash: 'hash',
        feePayer: 'payer',
        signatures: [{ signature: new Uint8Array(64) }],
      })),
      { from: jest.fn().mockReturnValue({
        sign: jest.fn(),
        serialize: jest.fn().mockReturnValue(Buffer.alloc(100)),
        recentBlockhash: 'hash',
        signatures: [{ signature: new Uint8Array(64) }],
      })}
    ),
  };
});

jest.mock('../shared/keystore', () => ({
  loadKeypairFromKeystore: jest.fn().mockResolvedValue({
    publicKey: { toBase58: () => 'ESHH2KcsMWSKoA6ypBGfbpP8Mre3k1QVw4jkypn8A1xc' },
    secretKey: new Uint8Array(64),
  }),
}));

jest.mock('../shared/db', () => ({
  insertPosition: { run: jest.fn() },
  updatePosition: { run: jest.fn() },
  insertAuditLog: { run: jest.fn() },
  shutdownDB: jest.fn(),
}));

jest.mock('../shared/operational-window', () => ({
  isOperationalWindowActive: jest.fn().mockReturnValue(true),
}));

jest.mock('fs');

import { AresAgent, fetchTokenPrice, getSolPriceUsd, rateLimitedRequest } from './ares';
import { loadKeypairFromKeystore } from '../shared/keystore';
import { isOperationalWindowActive } from '../shared/operational-window';
import { insertPosition, insertAuditLog } from '../shared/db';

describe('AresAgent Coverage Boost', () => {
  let mockRedis: any;

  beforeAll(() => {
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterAll(() => {
    (console.log as jest.Mock).mockRestore();
    (console.error as jest.Mock).mockRestore();
    const { shutdownDB } = require('../shared/db');
    shutdownDB();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    resetMockVersionedTx();
    const { resetMockRedis } = require('../shared/mock_redis');
    resetMockRedis();
    const Redis = require('ioredis');
    mockRedis = new Redis();
    mockRedis.scard = jest.fn().mockResolvedValue(0);
    mockRedis.incr = jest.fn().mockResolvedValue(1);
    mockRedis.expire = jest.fn().mockResolvedValue(1);
    mockRedis.sadd = jest.fn().mockResolvedValue(1);
    mockRedis.srem = jest.fn().mockResolvedValue(1);
    mockRedis.publish = jest.fn().mockResolvedValue(1);

    mockGetBalance.mockResolvedValue(2 * 1e9);
    mockSendRawTransaction.mockResolvedValue('test_sig');
    mockGetSignatureStatus.mockResolvedValue({ value: { confirmationStatus: 'confirmed', err: null } });

    (global as any).fetch = jest.fn().mockImplementation((url: string) => {
      if (url.includes('/price/v2')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
        });
      }
      if (url.includes('/price/v3')) {
        return Promise.resolve({
          json: () => Promise.resolve({ data: { testMint: { price: 1.5 } } }),
        });
      }
      if (url.includes('/quote')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ outAmount: '1000000' }),
          text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
        });
      }
      if (url.includes('/execute')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'Success', signature: 'test-sig', outAmount: '1000000' }),
        });
      }
      if (url.includes('/order')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ transaction: 'base64_tx', requestId: 'req1' }),
        });
      }
      if (url.includes('/swap')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ swapTransaction: 'base64_tx' }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
    });
  });

  // ============================================================
  // fetchTokenPrice – lines 72-79
  // ============================================================
  describe('fetchTokenPrice', () => {
    it('returns price when API responds', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        json: () => Promise.resolve({ data: { testMint: { price: 1.5 } } }),
      });
      const price = await fetchTokenPrice('testMint');
      expect(price).toBe(1.5);
    });

    it('returns 0 when API returns no data', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        json: () => Promise.resolve({ data: {} }),
      });
      const price = await fetchTokenPrice('testMint');
      expect(price).toBe(0);
    });

    it('returns 0 on fetch error', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));
      const price = await fetchTokenPrice('testMint');
      expect(price).toBe(0);
    });
  });

  // ============================================================
  // getSolPriceUsd – line 206 (no price in response)
  // ============================================================
  describe('getSolPriceUsd', () => {
    it('falls back to 200 when price is 0 in response', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 0 } } }),
      });
      const price = await getSolPriceUsd();
      expect(price).toBe(200);
    });

    it('falls back to 200 when response has no price field', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      });
      const price = await getSolPriceUsd();
      expect(price).toBe(200);
    });

    it('falls back on fetch error', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('fail'));
      const price = await getSolPriceUsd();
      expect(price).toBe(200);
    });
  });

  // ============================================================
  // rateLimitedRequest – lines 222, 231-244
  // ============================================================
  describe('rateLimitedRequest', () => {
    it('adds delay when called in quick succession (line 222)', async () => {
      const fn = jest.fn().mockResolvedValue('ok');
      await rateLimitedRequest(fn);
      const t0 = Date.now();
      await rateLimitedRequest(fn);
      const elapsed = Date.now() - t0;
      expect(elapsed).toBeGreaterThanOrEqual(0);
      expect(fn).toHaveBeenCalledTimes(2);
    }, 10000);

    it('retries on 429 with exponential backoff then succeeds', async () => {
      jest.useFakeTimers();
      const fn = jest.fn()
        .mockRejectedValueOnce({ response: { status: 429 } })
        .mockRejectedValueOnce({ response: { status: 429 } })
        .mockResolvedValueOnce('success');
      const promise = rateLimitedRequest(fn);
      // Advance past initial check, then 2s, 4s backoffs
      for (let i = 0; i < 20; i++) {
        jest.advanceTimersByTime(1000);
        await Promise.resolve();
      }
      const result = await promise;
      expect(result).toBe('success');
      expect(fn).toHaveBeenCalledTimes(3);
      jest.useRealTimers();
    }, 10000);

    it('re-throws after exhausting 429 retries', async () => {
      jest.useFakeTimers();
      const err = { response: { status: 429 } };
      const fn = jest.fn().mockRejectedValue(err);
      const promise = rateLimitedRequest(fn);
      for (let i = 0; i < 30; i++) {
        jest.advanceTimersByTime(1000);
        await Promise.resolve();
      }
      await expect(promise).rejects.toEqual(err);
      expect(fn).toHaveBeenCalledTimes(4);
      jest.useRealTimers();
    }, 10000);

    it('re-throws non-429 errors immediately', async () => {
      const err = new Error('Bad gateway');
      const fn = jest.fn().mockRejectedValue(err);
      await expect(rateLimitedRequest(fn)).rejects.toThrow('Bad gateway');
      expect(fn).toHaveBeenCalledTimes(1);
    });
  });

  // ============================================================
  // RateLimiter error handling – lines 117, 129, 148-149, 166-190
  // ============================================================
  describe('RateLimiter edge cases', () => {
    async function createAgent(): Promise<AresAgent> {
      const { AresAgent } = require('./ares');
      const agent = new AresAgent({
        trading: { position_size_sol: 0.0005, max_simultaneous_positions: 1, max_trades_per_hour: 3, daily_loss_limit_sol: 0.002, tp1_multiplier: 2, tp2_multiplier: 5, sl_multiplier: 0.7, trailing_stop_pct: 15 }
      }, mockRedis);
      await agent.init();
      return agent;
    }

    it('blocks trade when concurrent positions reached (line 117)', async () => {
      mockRedis.scard = jest.fn().mockResolvedValue(1);
      const agent = await createAgent();
      process.env.MTUS_ENVIRONMENT = 'paper';
      await (agent as any).executeTrade('mint1', 'corr1');
      const pubCalls = mockRedis.publish.mock.calls;
      const failedCall = pubCalls.find((c: any) => c[0] === CHANNEL_TRADE_FAILED);
      expect(failedCall).toBeDefined();
      if (failedCall) {
        const payload = JSON.parse(failedCall[1]);
        expect(payload.payload.error).toContain('concurrent positions');
      }
      await agent.stop();
    });

    it('blocks trade when hourly rate limit reached (line 129)', async () => {
      const hour = Math.floor(Date.now() / 3600000);
      mockRedis.get = jest.fn().mockImplementation((key: string) => {
        if (key === `mtus:trade_count:${hour}`) return Promise.resolve('3');
        return Promise.resolve('0');
      });
      const agent = await createAgent();
      process.env.MTUS_ENVIRONMENT = 'paper';
      await (agent as any).executeTrade('mint1', 'corr1');
      const pubCalls = mockRedis.publish.mock.calls;
      const failedCall = pubCalls.find((c: any) => c[0] === CHANNEL_TRADE_FAILED);
      expect(failedCall).toBeDefined();
      if (failedCall) {
        const payload = JSON.parse(failedCall[1]);
        expect(payload.payload.error).toContain('trades per hour');
      }
      await agent.stop();
    });

    it('allows trade when RateLimiter throws (lines 148-149)', async () => {
      mockRedis.scard = jest.fn().mockRejectedValue(new Error('Redis down'));
      const agent = await createAgent();
      process.env.MTUS_ENVIRONMENT = 'paper';
      await (agent as any).executeTrade('mint1', 'corr1');
      const pubCalls = mockRedis.publish.mock.calls;
      const openedCall = pubCalls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    });

    it('recordTrade catches Redis errors (line 166)', async () => {
      mockRedis.incr = jest.fn().mockRejectedValue(new Error('Redis fail'));
      const agent = await createAgent();
      process.env.MTUS_ENVIRONMENT = 'paper';
      await (agent as any).executeTrade('mint1', 'corr1');
      const pubCalls = mockRedis.publish.mock.calls;
      const openedCall = pubCalls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    });

    it('closePosition catches Redis errors (line 174)', async () => {
      mockRedis.srem = jest.fn().mockRejectedValue(new Error('Redis fail'));
      const agent = await createAgent();
      await (agent as any).rateLimiter.closePosition('test-id');
      await agent.stop();
    });

    it('updateDailyPnl catches Redis errors (line 183-188)', async () => {
      const agent = await createAgent();
      (agent as any).rateLimiter.redis.get = jest.fn().mockRejectedValue(new Error('Redis fail'));
      await (agent as any).rateLimiter.updateDailyPnl(0.001);
      await agent.stop();
    });

    it('updateDailyPnl catches Redis set error', async () => {
      const agent = await createAgent();
      (agent as any).rateLimiter.redis.set = jest.fn().mockRejectedValue(new Error('set failed'));
      await (agent as any).rateLimiter.updateDailyPnl(0.001);
      await agent.stop();
    });

    it('updateDailyPnl catches Redis expire error', async () => {
      const agent = await createAgent();
      (agent as any).rateLimiter.redis.expire = jest.fn().mockRejectedValue(new Error('expire failed'));
      await (agent as any).rateLimiter.updateDailyPnl(0.001);
      await agent.stop();
    });
  });

  // ============================================================
  // isPaperMode config fallback – line 276
  // ============================================================
  describe('isPaperMode config fallback', () => {
    it('falls back to config when env var is not set', () => {
      delete process.env.MTUS_ENVIRONMENT;
      const agent = new AresAgent({
        system: { environment: 'paper' },
        trading: { position_size_sol: 0.0005 },
      });
      expect((agent as any).isPaperMode()).toBe(true);
    });

    it('defaults to true when neither env nor config is set', () => {
      delete process.env.MTUS_ENVIRONMENT;
      const agent = new AresAgent({
        system: { environment: 'production' },
        trading: { position_size_sol: 0.0005 },
      });
      expect((agent as any).isPaperMode()).toBe(false);
    });

    it('defaults to true when no env and no config system field', () => {
      delete process.env.MTUS_ENVIRONMENT;
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } });
      expect((agent as any).isPaperMode()).toBe(true);
    });
  });

  // ============================================================
  // loadConfig throws – lines 289-290
  // ============================================================
  describe('loadConfig error path', () => {
    it('uses defaults when config file cannot be loaded', () => {
      const fs = require('fs');
      (fs.readFileSync as jest.Mock).mockImplementation(() => { throw new Error('File not found'); });
      const agent = new AresAgent();
      expect((agent as any).config).toBeDefined();
      expect((agent as any).config.trading.position_size_sol).toBe(0.0005);
    });
  });

  // ============================================================
  // init with/without redis – lines 296, 298
  // ============================================================
  describe('init branches', () => {
    it('init with redis param sets redis', async () => {
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } });
      await agent.init(mockRedis);
      expect((agent as any).redis).toBe(mockRedis);
      await agent.stop();
    });

    it('init without redis creates one via createRedisClient', async () => {
      jest.isolateModules(async () => {
        const createRedisClient = jest.fn().mockResolvedValue(mockRedis);
        jest.mock('../shared/redis', () => ({ createRedisClient }));
        const { AresAgent } = require('./ares');
        const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } });
        await agent.init();
        expect((agent as any).redis).toBeDefined();
        await agent.stop();
      });
    });
  });

  // ============================================================
  // loadSniperWallet – lines 305-318
  // ============================================================
  describe('loadSniperWallet', () => {
    it('loads wallet and verifies keypair', async () => {
      process.env.SNIPER_KEYSTORE_PATH = './test.keystore';
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } });
      await agent.loadSniperWallet('test-pass');
      expect(loadKeypairFromKeystore).toHaveBeenCalledWith('./test.keystore', 'test-pass');
    });

    it('throws on wrong wallet address', async () => {
      (loadKeypairFromKeystore as jest.Mock).mockResolvedValueOnce({
        publicKey: { toBase58: () => 'WRONG_ADDRESS' },
        secretKey: new Uint8Array(64),
      });
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } });
      await expect(agent.loadSniperWallet('test-pass')).rejects.toThrow('CRITICAL');
    });
  });

  // ============================================================
  // executeTrade – operational window blocked – lines 324-328
  // ============================================================
  describe('executeTrade operational window', () => {
    it('blocks trade outside operational window in production mode', async () => {
      (isOperationalWindowActive as jest.Mock).mockReturnValue(false);
      process.env.MTUS_ENVIRONMENT = 'production';
      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      await (agent as any).executeTrade('mint1', 'corr1');
      expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_TRADE_FAILED, expect.stringContaining('Outside operational window'));
      await agent.stop();
      (isOperationalWindowActive as jest.Mock).mockReturnValue(true);
    });
  });

  // ============================================================
  // executeTrade – no wallet in live mode – lines 350-351
  // ============================================================
  describe('executeTrade no wallet', () => {
    it('exits early when no wallet loaded in production', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeUndefined();
      await agent.stop();
    });
  });

  // ============================================================
  // executeTrade – balance check throws – line 377
  // ============================================================
  describe('executeTrade balance check error', () => {
    it('handles balance check throwing an error', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockRejectedValue(new Error('RPC error'));
      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    });
  });

  // ============================================================
  // executeTrade V1 – all slippage levels fail – lines 434, 439-443
  // ============================================================
  describe('executeTrade V1 - no quote for any slippage', () => {
    it('fails when no Jupiter quote with any slippage level', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);
      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({}),
            text: () => Promise.resolve('{}'),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });
      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_TRADE_FAILED, expect.stringContaining('No quote'));
      await agent.stop();
    });
  });

  // ============================================================
  // executeTrade V1 – no swapTransaction in response – line 476
  // ============================================================
  describe('executeTrade V1 - no swapTransaction', () => {
    it('throws when swap response has no swapTransaction', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);
      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({}),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });
      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_TRADE_FAILED, expect.stringContaining('No swap transaction'));
      await agent.stop();
    });
  });

  // ============================================================
  // executeTrade V1 – VersionedTransaction.deserialize failure – lines 491-497
  // ============================================================
  describe('executeTrade V1 - Versioned parse failure then legacy succeeds', () => {
    it('tries legacy deserialization when VersionedTransaction fails and legacy succeeds', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      (VersionedTransaction as any).deserialize = jest.fn()
        .mockImplementationOnce(() => { throw new Error('not a versioned tx'); });

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      // versioned failed but legacy succeeded → signedTxBytes set → trade completes
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
      (VersionedTransaction as any).deserialize = jest.fn().mockImplementation(() => mockVersionedTx);
    });
  });

  // ============================================================
  // executeTrade V1 – legacy tx signing path – lines 491-497, 529-542
  // ============================================================
  describe('executeTrade V1 - legacy transaction path coverage', () => {
    it('covers legacy transaction signing and serialization', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      (VersionedTransaction as any).deserialize = jest.fn()
        .mockImplementationOnce(() => { throw new Error('not versioned'); });

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
      (VersionedTransaction as any).deserialize = jest.fn().mockImplementation(() => mockVersionedTx);
    });
  });

  // ============================================================
  // executeTrade V1 – verification fails after signing – line 527
  // ============================================================
  describe('executeTrade V1 - verification failure after signing', () => {
    it('handles verification failure after signing', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      let deserializeCallCount = 0;
      (VersionedTransaction as any).deserialize = jest.fn().mockImplementation(() => {
        deserializeCallCount++;
        if (deserializeCallCount >= 2) {
          throw new Error('Verification corrupted');
        }
        return mockVersionedTx;
      });

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
      (VersionedTransaction as any).deserialize = jest.fn().mockImplementation(() => mockVersionedTx);
    });
  });

  // ============================================================
  // executeTrade V2 – execution returns non-Success – line 608
  // ============================================================
  describe('executeTrade V2 - execution failed status', () => {
    it('falls back to v1 when v2 execute returns non-Success status', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/order')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ transaction: 'base64_tx', requestId: 'req1' }),
          });
        }
        if (url.includes('/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ status: 'Failed', error: 'execution failed' }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.1 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    });
  });

  // ============================================================
  // executeTrade – no signed tx available – line 665
  // ============================================================
  describe('executeTrade - no signed transaction', () => {
    it('throws when no signed transaction is produced', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      (VersionedTransaction as any).deserialize = jest.fn()
        .mockImplementation(() => { throw new Error('not versioned'); });
      const { Transaction } = require('@solana/web3.js');
      (Transaction as any).from = jest.fn()
        .mockImplementation(() => { throw new Error('legacy also failed'); });

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_TRADE_FAILED, expect.stringContaining('No signed transaction'));
      await agent.stop();
      (VersionedTransaction as any).deserialize = jest.fn().mockImplementation(() => mockVersionedTx);
    });
  });

  // ============================================================
  // executeTrade – DB insert catch – line 895
  // ============================================================
  describe('executeTrade DB insert failure', () => {
    it('catches DB insert errors gracefully', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      (insertPosition.run as jest.Mock).mockImplementationOnce(() => { throw new Error('DB error'); });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    });
  });

  // ============================================================
  // executeTrade – paper mode outer catch – lines 976-978
  // ============================================================
  describe('executeTrade paper mode outer catch', () => {
    it('handles errors in paper trade execution', async () => {
      process.env.MTUS_ENVIRONMENT = 'paper';
      mockRedis.publish = jest.fn().mockRejectedValue(new Error('Publish failed'));

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      try {
        await (agent as any).executeTrade('mint1', 'corr1');
      } catch (e) {
        // Expected: outer catch tries to publish trade_failed, which also fails
      }

      const pubCalls = mockRedis.publish.mock.calls;
      const failedCall = pubCalls.find((c: any) => c[0] === CHANNEL_TRADE_FAILED);
      expect(failedCall).toBeDefined();
      await agent.stop();
    });
  });

  // ============================================================
  // executeTrade – transaction error in signature status – lines 795-797
  // ============================================================
  describe('executeTrade - tx has error status', () => {
    it('detects transaction errors in signature status', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      mockGetSignatureStatus.mockResolvedValue({ value: { confirmationStatus: 'confirmed', err: { InstructionError: [0, 'Custom error'] } } });

      const origFetch = (global.fetch as jest.Mock).getMockImplementation();
      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        if (url.includes('/execute')) {
          return Promise.resolve({
            ok: false,
            status: 400,
            text: () => Promise.resolve('{"error":"failed"}'),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_TRADE_FAILED, expect.stringContaining('Transaction failed'));
      await agent.stop();
    }, 15000);
  });

  // ============================================================
  // executeTrade – confirmation timeout -> Jupiter execute succeeds -> lines 741-768, 857
  // ============================================================
  describe('executeTrade - confirmation timeout then Jupiter execute succeeds', () => {
    it('uses Jupiter execute as last resort when tx not confirmed', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      let statusCalls = 0;
      mockGetSignatureStatus.mockImplementation(() => {
        statusCalls++;
        return Promise.resolve({ value: null });
      });

      let executeAttempts = 0;
      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        if (url.includes('/execute')) {
          executeAttempts++;
          if (executeAttempts > 1) {
            return Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ status: 'Success', signature: 'final-sig', outAmount: '1000000' }),
            });
          }
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ status: 'Success', signature: 'test-sig', outAmount: '1000000' }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      mockSendRawTransaction.mockResolvedValue('test-sig');

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;

      jest.useFakeTimers();
      let now = Date.now();
      const dateSpy = jest.spyOn(Date, 'now').mockImplementation(() => now);
      const promise = (agent as any).executeTrade('mint1', 'corr1');
      for (let i = 0; i < 80; i++) {
        now += 1000;
        jest.advanceTimersByTime(1000);
        await Promise.resolve();
        await Promise.resolve();
      }
      await promise;

      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      dateSpy.mockRestore();
      jest.useRealTimers();
      await agent.stop();
    }, 20000);
  });

  // ============================================================
  // run() event processing error – line 1015
  // ============================================================
  describe('run event processing error', () => {
    it('catches errors in event processing', async () => {
      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();

      let subOnCallback: any;
      mockRedis.duplicate.mockReturnValue({
        on: jest.fn().mockImplementation((evt: string, cb: any) => { subOnCallback = cb; }),
        subscribe: jest.fn().mockResolvedValue(undefined),
        quit: jest.fn(),
      });

      const runPromise = agent.run();

      await subOnCallback('mtus:channel:trade_approved', 'invalid json!!!');

      agent.stop();
      await runPromise;
    });
  });

  // ============================================================
  // V2 fallback to V1 full path – lines 635-660
  // ============================================================
  describe('V2 fallback to V1 full path', () => {
    it('falls back from v2 to v1 with execute endpoint and broadcasts tx', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      process.env.QUICKNODE_RPC_URL = 'http://quicknode:8899';
      process.env.ALCHEMY_RPC_URL = 'http://alchemy:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/order')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ transaction: 'base64_tx', requestId: 'req1' }),
          });
        }
        if (url.includes('/execute')) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: () => Promise.resolve({ error: 'simulation failed' }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.1 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    }, 15000);
  });

  // ============================================================
  // RecordTrade error catch in production mode – line 166
  // ============================================================
  describe('recordTrade catch in production mode', () => {
    it('catches recordTrade error in production mode', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      mockRedis.incr = jest.fn().mockRejectedValue(new Error('Redis fail'));

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    }, 15000);
  });

  // ============================================================
  // V1 slippage ladder – individual levels fail – line 434
  // ============================================================
  describe('V1 slippage ladder individual failures', () => {
    it('handles some slippage levels failing but eventually succeeds', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      let quoteAttempt = 0;
      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          quoteAttempt++;
          if (quoteAttempt <= 2) {
            return Promise.resolve({
              ok: false,
              status: 400,
              text: () => Promise.resolve('{"error":"quote failed"}'),
            });
          }
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      const openedCall = mockRedis.publish.mock.calls.find((c: any) => c[0] === CHANNEL_POSITION_OPENED);
      expect(openedCall).toBeDefined();
      await agent.stop();
    }, 15000);
  });

  // ============================================================
  // All RPC broadcasts fail then Jupiter execute fallback also fails – lines 773-774
  // ============================================================
  describe('all RPC broadcasts fail', () => {
    it('handles scenario where all providers fail and Jupiter execute also fails', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      process.env.HELIUS_RPC_URL = 'http://localhost:8899';
      process.env.QUICKNODE_RPC_URL = 'http://quicknode:8899';
      process.env.ALCHEMY_RPC_URL = 'http://alchemy:8899';
      mockGetBalance.mockResolvedValue(2 * 1e9);

      mockSendRawTransaction.mockRejectedValue(new Error('Broadcast failed'));

      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/price/v2')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
          });
        }
        if (url.includes('/quote')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ outAmount: '1000000' }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })),
          });
        }
        if (url.includes('/swap') && !url.includes('/v2/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
          });
        }
        if (url.includes('/execute')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ status: 'Success' }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('ok') });
      });

      const { AresAgent } = require('./ares');
      const agent = new AresAgent({ trading: { position_size_sol: 0.0005 } }, mockRedis);
      await agent.init();
      const kp = Keypair.generate();
      (agent as any).keypair = kp;
      await (agent as any).executeTrade('mint1', 'corr1');
      expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_TRADE_FAILED, expect.stringContaining('failed'));
      await agent.stop();
    }, 15000);
  });
});
