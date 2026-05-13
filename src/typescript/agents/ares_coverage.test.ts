import * as db from '../shared/db';
import * as keystore from '../shared/keystore';
import { Keypair, Connection, VersionedTransaction, PublicKey } from '@solana/web3.js';
import Redis from 'ioredis';

// Global mocks
const mockGetBalance = jest.fn().mockResolvedValue(1000000000);
const mockSendRawTransaction = jest.fn().mockResolvedValue('test_sig');
const mockGetSignatureStatus = jest.fn().mockResolvedValue({ value: { confirmationStatus: 'confirmed' } });

jest.mock('../shared/db', () => ({
  insertPosition: { run: jest.fn() },
  updatePosition: { run: jest.fn() },
  insertAuditLog: { run: jest.fn() },
  getOpenPositions: { run: jest.fn() },
  shutdownDB: jest.fn(),
}));

jest.mock('ioredis', () => require('../shared/mock_redis').default);
jest.mock('../shared/keystore');

jest.mock('@solana/web3.js', () => {
  const actual = jest.requireActual('@solana/web3.js');
  return {
    ...actual,
    Connection: jest.fn().mockImplementation(() => ({
      getBalance: mockGetBalance,
      sendRawTransaction: mockSendRawTransaction,
      getSignatureStatus: mockGetSignatureStatus,
    })),
    VersionedTransaction: {
        deserialize: jest.fn().mockReturnValue({
            sign: jest.fn(),
            serialize: jest.fn().mockReturnValue(new Uint8Array(64)),
            message: { recentBlockhash: 'hash', version: 'legacy' },
            signatures: [new Uint8Array(64)]
        }),
    }
  };
});

describe('AresAgent Coverage Tests', () => {
  let mockRedis: any;

  beforeEach(() => {
    jest.clearAllMocks();
    const { resetMockRedis } = require('../shared/mock_redis');
    resetMockRedis();
    const Redis = require('ioredis');
    mockRedis = new Redis();
    
    mockRedis.publish = jest.fn();
    mockRedis.scard = jest.fn().mockResolvedValue(0);
    mockRedis.get = jest.fn().mockResolvedValue(null);
    mockRedis.set = jest.fn();
    mockRedis.incr = jest.fn();
    mockRedis.expire = jest.fn();
    mockRedis.sadd = jest.fn();
    mockRedis.srem = jest.fn();

    mockGetBalance.mockResolvedValue(1000000000);
    mockSendRawTransaction.mockResolvedValue('test_sig');

    (global as any).fetch = jest.fn().mockImplementation((url: string) => {
        const mockResponse = {
            ok: true,
            json: () => Promise.resolve({ 
                data: { 'So11111111111111111111111111111111111111112': { price: 200 } },
                outAmount: '1000000',
                swapTransaction: Buffer.from(new Uint8Array(64)).toString('base64'),
                status: 'Success',
                signature: 'test_sig'
            }),
            text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000', swapTransaction: Buffer.from(new Uint8Array(64)).toString('base64') }))
        };
        return Promise.resolve(mockResponse);
    });

    const ow = require('../shared/operational-window');
    jest.spyOn(ow, 'isOperationalWindowActive').mockReturnValue(true);
  });

  afterEach(() => {
      jest.restoreAllMocks();
  });

  test('init agent', async () => {
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({}, mockRedis);
    await agent.init();
    expect(agent).toBeDefined();
  });

  test('loadSniperWallet success', async () => {
    const { AresAgent } = require('./ares');
    const kp = Keypair.generate();
    (keystore.loadKeypairFromKeystore as jest.Mock).mockResolvedValue(kp);
    
    const agent = new AresAgent({}, mockRedis);
    const spy = jest.spyOn(PublicKey.prototype, 'toBase58').mockReturnValue("ESHH2KcsMWSKoA6ypBGfbpP8Mre3k1QVw4jkypn8A1xc");

    await agent.loadSniperWallet('pass');
    expect(agent['keypair']).toBe(kp);
    spy.mockRestore();
  });

  test('executeTrade paper mode blocked by rate limit', async () => {
    process.env.MTUS_ENVIRONMENT = 'paper';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({}, mockRedis);
    
    mockRedis.scard.mockResolvedValue(10); // Max is 1
    
    await agent.executeTrade('mint1', 'corr1');
    expect(mockRedis.publish).toHaveBeenCalledWith(expect.any(String), expect.stringContaining('Max concurrent positions'));
  });

  test('executeTrade live mode blocked by operational window', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({}, mockRedis);
    
    const ow = require('../shared/operational-window');
    (ow.isOperationalWindowActive as jest.Mock).mockReturnValue(false);

    await agent.executeTrade('mint1', 'corr1');
    expect(mockRedis.publish).toHaveBeenCalledWith(expect.any(String), expect.stringContaining('Outside operational window'));
  });

  test('executeTrade live mode insufficient balance', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({}, mockRedis);
    agent['keypair'] = Keypair.generate();
    
    const ow = require('../shared/operational-window');
    (ow.isOperationalWindowActive as jest.Mock).mockReturnValue(true);

    mockGetBalance.mockResolvedValue(0);

    await agent.executeTrade('mint1', 'corr1');
    expect(mockRedis.publish).toHaveBeenCalledWith(expect.any(String), expect.stringContaining('Insufficient balance'));
  });

  test('executeTrade live mode successful v1 trade', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    process.env.HELIUS_RPC_URL = 'https://helius.com';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({ trading: { position_size_sol: 0.001 } }, mockRedis);
    agent['keypair'] = Keypair.generate();
    
    const ow = require('../shared/operational-window');
    (ow.isOperationalWindowActive as jest.Mock).mockReturnValue(true);
    mockGetBalance.mockResolvedValue(2000000000);

    await agent.executeTrade('mint1', 'corr1');
    const failedCalls = mockRedis.publish.mock.calls.filter((c: any) => c[0].includes('trade_failed'));
    expect(failedCalls.length).toBe(0);
  });

  test('executeTrade live mode successful v2 trade', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({ trading: { position_size_sol: 1.0 } }, mockRedis); // $200 value
    agent['keypair'] = Keypair.generate();
    
    const ow = require('../shared/operational-window');
    (ow.isOperationalWindowActive as jest.Mock).mockReturnValue(true);
    mockGetBalance.mockResolvedValue(2000000000);

    (global as any).fetch = jest.fn().mockImplementation((url: string) => {
        if (url.includes('/price/v2')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { price: 200 } } }) });
        if (url.includes('/swap/v2/order')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ transaction: Buffer.from(new Uint8Array(64)).toString('base64'), requestId: 'req1' }) });
        if (url.includes('/swap/v2/execute')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'Success', signature: 'v2_sig', outAmount: '2000000' }) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await agent.executeTrade('mint1', 'corr1');
    expect(mockRedis.publish).not.toHaveBeenCalledWith(expect.any(String), expect.stringContaining('trade_failed'));
  });

  test('executeTrade live mode v2 fallback to v1', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({ trading: { position_size_sol: 1.0 } }, mockRedis);
    agent['keypair'] = Keypair.generate();
    
    const ow = require('../shared/operational-window');
    (ow.isOperationalWindowActive as jest.Mock).mockReturnValue(true);
    mockGetBalance.mockResolvedValue(2000000000);

    (global as any).fetch = jest.fn().mockImplementation((url: string) => {
        if (url.includes('/price/v2')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { price: 200 } } }) });
        if (url.includes('/swap/v2/order')) return Promise.resolve({ ok: false, status: 500 }); // V2 FAIL
        if (url.includes('/swap/v1/quote')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ outAmount: '1000000' }) });
        if (url.includes('/swap/v1/swap')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(64)).toString('base64') }) });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await agent.executeTrade('mint1', 'corr1');
    expect(mockSendRawTransaction).toHaveBeenCalled();
  });

  test('utility functions', async () => {
      const { getSolPriceUsd, getJupiterApiVersion, fetchTokenPrice } = require('./ares');
      
      (global as any).fetch = jest.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { price: 150 } } })
      });
      
      const price = await getSolPriceUsd();
      expect(price).toBe(150);
      
      const jup = await getJupiterApiVersion(1.0);
      expect(jup.version).toBe('v2');
      expect(jup.usdValue).toBe(150);

      (global as any).fetch = jest.fn().mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ data: { 'mint1': { price: 0.5 } } })
      });
      const tPrice = await fetchTokenPrice('mint1');
      expect(tPrice).toBe(0.5);
  });

  test('rateLimitedRequest handles 429', async () => {
    const { rateLimitedRequest } = require('./ares');
    const reqFn = jest.fn()
        .mockRejectedValueOnce({ response: { status: 429 } })
        .mockResolvedValueOnce('ok');
    
    const res = await rateLimitedRequest(reqFn);
    expect(res).toBe('ok');
    expect(reqFn).toHaveBeenCalledTimes(2);
  });

  test('createRedisClient fallback', async () => {
    const { createRedisClient } = require('./ares');
    const Redis = require('ioredis');
    jest.spyOn(Redis.prototype, 'ping').mockRejectedValue(new Error('fail'));
    
    const client = await createRedisClient();
    expect(client.constructor.name).toBe('MockRedis');
  });

  test('canAffordTrade utility', async () => {
      const { canAffordTrade } = require('./ares');
      const conn = new Connection('url');
      mockGetBalance.mockResolvedValue(2000000000);
      const res = await canAffordTrade(conn, PublicKey.unique(), 0.001);
      expect(res.ok).toBe(true);
  });

  test('executeTrade handles simulation failure and fallback', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({ trading: { position_size_sol: 0.001 } }, mockRedis);
    agent['keypair'] = Keypair.generate();
    
    mockGetBalance.mockResolvedValue(2000000000);
    mockSendRawTransaction.mockRejectedValueOnce(new Error('Simulation failed'));
    mockSendRawTransaction.mockResolvedValueOnce('retry_sig');

    await agent.executeTrade('mint1', 'corr1');
    expect(mockRedis.publish).not.toHaveBeenCalledWith(expect.any(String), expect.stringContaining('trade_failed'));
  });

  test('executeTrade handles total broadcast failure', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    const { AresAgent } = require('./ares');
    const agent = new AresAgent({ trading: { position_size_sol: 0.001 } }, mockRedis);
    agent['keypair'] = Keypair.generate();
    
    mockGetBalance.mockResolvedValue(2000000000);
    mockSendRawTransaction.mockRejectedValue(new Error('Network error'));
    
    (global as any).fetch = jest.fn().mockImplementation((url: string) => {
        if (url.includes('/swap/v1/quote')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ outAmount: '1000000' }), text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' })) });
        if (url.includes('/swap/v1/swap')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(64)).toString('base64') }), text: () => Promise.resolve(JSON.stringify({ swapTransaction: Buffer.from(new Uint8Array(64)).toString('base64') })) });
        if (url.includes('/swap/v2/execute')) return Promise.resolve({ ok: false, status: 500, text: () => Promise.resolve('Error') });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}), text: () => Promise.resolve('{}') });
    });

    await agent.executeTrade('mint1', 'corr1');
    expect(mockRedis.publish).toHaveBeenCalledWith(expect.any(String), expect.stringContaining('trade_failed'));
  });
});
