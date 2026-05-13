import { Keypair } from '@solana/web3.js';
import * as channels from '../shared/channels';

// Shared mocks to ensure consistency across Connection instances
const mockGetSignatureStatus = jest.fn().mockResolvedValue({ value: { confirmationStatus: 'confirmed', err: null } });
const mockSendRawTransaction = jest.fn().mockResolvedValue('test_sig');
const mockGetBalance = jest.fn().mockResolvedValue(1 * 1e9);
const mockGetLatestBlockhash = jest.fn().mockResolvedValue({ blockhash: 'hash', lastValidBlockHeight: 1000 });

// Mock Redis
jest.mock('ioredis', () => {
  const MockRedis = require('../shared/mock_redis').default;
  const originalDuplicate = MockRedis.prototype.duplicate;
  MockRedis.prototype.duplicate = jest.fn().mockImplementation(function(this: any) {
    const d = originalDuplicate.call(this);
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

// Mock Jupiter API
jest.mock('@jup-ag/api', () => ({
  QuoteResponse: {},
  SwapApi: jest.fn().mockImplementation(() => ({
    quoteGet: jest.fn().mockResolvedValue({ outAmount: '1000000' }),
    swapPost: jest.fn().mockResolvedValue({ swapTransaction: 'base64_tx' }),
  })),
}));

// Mock Web3
jest.mock('@solana/web3.js', () => {
  const actual = jest.requireActual('@solana/web3.js');
  
  const mockTx = {
    sign: jest.fn(),
    serialize: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3])),
    message: { recentBlockhash: 'hash', version: 0 },
    signatures: [new Uint8Array(64)]
  };

  const VersionedTransaction = jest.fn().mockImplementation(() => mockTx);
  (VersionedTransaction as any).deserialize = jest.fn().mockReturnValue(mockTx);

  return {
    ...actual,
    Connection: jest.fn().mockImplementation(() => ({
      getBalance: mockGetBalance,
      getLatestBlockhash: mockGetLatestBlockhash,
      sendRawTransaction: mockSendRawTransaction,
      getSignatureStatus: mockGetSignatureStatus,
      onSignature: jest.fn((sig, cb) => cb({ err: null }, { slot: 1 })),
      removeSignatureListener: jest.fn(),
      confirmTransaction: jest.fn().mockResolvedValue({ value: { err: null } }),
    })),
    VersionedTransaction
  };
});

// Mock shared modules
jest.mock('../shared/keystore', () => ({
  loadKeypairFromKeystore: jest.fn(),
}));

jest.mock('../shared/db', () => ({
  insertPosition: { run: jest.fn() },
  updatePosition: { run: jest.fn() },
  insertAuditLog: { run: jest.fn() },
  shutdownDB: jest.fn(),
}));

jest.mock('../shared/operational-window', () => ({
  isOperationalWindowActive: jest.fn().mockReturnValue(true)
}));

describe('AresAgent Rigorous Tests', () => {
  let mockRedis: any;

  beforeAll(() => {
    // jest.spyOn(console, 'log').mockImplementation(() => {});
    // jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterAll(() => {
    if ((console.log as any).mockRestore) (console.log as any).mockRestore();
    if ((console.error as any).mockRestore) (console.error as any).mockRestore();
    const { shutdownDB } = require('../shared/db');
    shutdownDB();
  });

  beforeEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
    const { resetMockRedis } = require('../shared/mock_redis');
    resetMockRedis();
    const Redis = require('ioredis');
    mockRedis = new Redis();
    
    // Reset mock defaults
    mockGetSignatureStatus.mockResolvedValue({ value: { confirmationStatus: 'confirmed', err: null } });
    mockSendRawTransaction.mockResolvedValue('test_sig');
    mockGetBalance.mockResolvedValue(1 * 1e9);
    
    // Mock global fetch
    (global as any).fetch = jest.fn().mockImplementation((url: string) => {
      if (url.includes('/price/v2')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } })
        });
      }
      if (url.includes('/quote')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ outAmount: '1000000' }),
          text: () => Promise.resolve(JSON.stringify({ outAmount: '1000000' }))
        });
      }
      if (url.includes('/execute')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: 'Success', signature: 'test-sig', outAmount: '1000000' })
        });
      }
      if (url.includes('/order')) {
          return Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ transaction: 'base64_tx', requestId: 'req1' })
          });
      }
      if (url.includes('/swap')) {
          return Promise.resolve({
              ok: true,
              json: () => Promise.resolve({ swapTransaction: 'base64_tx' })
          });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
        text: () => Promise.resolve('ok')
      });
    });
  });

  test('Production mode execution (Live v1 Path)', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    process.env.SNIPER_KEYSTORE_PATH = 'dummy_path';
    process.env.HELIUS_RPC_URL = 'http://localhost:8899';
    
    let AresAgent: any;
    jest.isolateModules(() => {
      AresAgent = require('./ares').AresAgent;
    });

    const agent = new AresAgent({
      trading: { position_size_sol: 0.01 } // 0.01 * 200 = 2 < 6 -> v1
    }, mockRedis);
    await agent.init();

    const testKeypair = Keypair.generate();
    jest.spyOn(agent, 'loadSniperWallet').mockImplementation(async () => {
      agent['keypair'] = testKeypair;
    });
    await agent.loadSniperWallet('passphrase');

    const mint = 'TokenMint11111111111111111111111111111111111';
    await agent.executeTrade(mint, 'prod-v1-corr-1');

    const publishCalls = mockRedis.publish.mock.calls;
    const publishedChannels = publishCalls.map((c: any) => c[0]);
    expect(publishedChannels).toContain(channels.CHANNEL_POSITION_OPENED);
    
    await agent.stop();
  });

  test('Paper mode execution', async () => {
    process.env.MTUS_ENVIRONMENT = 'paper';
    let AresAgent: any;
    jest.isolateModules(() => {
      AresAgent = require('./ares').AresAgent;
    });

    const agent = new AresAgent({
      trading: { position_size_sol: 0.1 }
    }, mockRedis);
    await agent.init();

    const mint = 'TokenMint11111111111111111111111111111111111';
    await agent.executeTrade(mint, 'paper-corr-1');

    const publishCalls = mockRedis.publish.mock.calls;
    expect(publishCalls.some((c: any) => c[0] === channels.CHANNEL_POSITION_OPENED)).toBe(true);
    
    await agent.stop();
  });

  test('Rate limiting - daily loss reached', async () => {
    process.env.MTUS_ENVIRONMENT = 'paper';
    let AresAgent: any;
    jest.isolateModules(() => {
      AresAgent = require('./ares').AresAgent;
    });

    const agent = new AresAgent({
      trading: { position_size_sol: 0.1, daily_loss_limit_sol: 0.1 }
    }, mockRedis);
    await agent.init();

    mockRedis.get.mockImplementation((key: string) => {
        if (key === 'mtus:daily_pnl') return Promise.resolve('-0.5');
        return Promise.resolve('0');
    });

    const mint = 'TokenMint11111111111111111111111111111111111';
    await agent.executeTrade(mint, 'blocked-corr-1');

    const publishCalls = mockRedis.publish.mock.calls;
    expect(publishCalls.some((c: any) => c[0] === channels.CHANNEL_TRADE_FAILED)).toBe(true);
    
    await agent.stop();
  });

  test('Production mode execution (Live v2 Path)', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    process.env.SNIPER_KEYSTORE_PATH = 'dummy_path';
    process.env.HELIUS_RPC_URL = 'http://localhost:8899';
    
    let AresAgent: any;
    jest.isolateModules(() => {
      AresAgent = require('./ares').AresAgent;
    });

    const agent = new AresAgent({
      trading: { position_size_sol: 0.1 } // 0.1 * 200 = 20 >= 6 -> v2
    }, mockRedis);
    await agent.init();

    const testKeypair = Keypair.generate();
    jest.spyOn(agent, 'loadSniperWallet').mockImplementation(async () => {
      agent['keypair'] = testKeypair;
    });
    await agent.loadSniperWallet('passphrase');

    const mint = 'TokenMint11111111111111111111111111111111111';
    await agent.executeTrade(mint, 'prod-v2-corr-1');

    const publishCalls = mockRedis.publish.mock.calls;
    expect(publishCalls.some((c: any) => c[0] === channels.CHANNEL_POSITION_OPENED)).toBe(true);
    
    await agent.stop();
  });

  test('Production mode execution (V2 Fallback to V1)', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    let AresAgent: any;
    jest.isolateModules(() => {
      AresAgent = require('./ares').AresAgent;
    });

    const agent = new AresAgent({
      trading: { position_size_sol: 0.1 }
    }, mockRedis);
    await agent.init();

    const testKeypair = Keypair.generate();
    jest.spyOn(agent, 'loadSniperWallet').mockImplementation(async () => {
      agent['keypair'] = testKeypair;
    });
    await agent.loadSniperWallet('passphrase');

    // Force V2 /order to fail
    (global as any).fetch.mockImplementationOnce(() => Promise.resolve({ ok: false, status: 500 }));

    const mint = 'TokenMint11111111111111111111111111111111111';
    await agent.executeTrade(mint, 'fallback-corr-1');

    const publishCalls = mockRedis.publish.mock.calls;
    // Should still open position via V1 path
    expect(publishCalls.some((c: any) => c[0] === channels.CHANNEL_POSITION_OPENED)).toBe(true);
    
    await agent.stop();
  });
});
