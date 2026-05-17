import * as fs from 'fs';
import axios from 'axios';
import { Transaction, PublicKey, SystemProgram, Keypair } from '@solana/web3.js';

const SHARED_KEYPAIR = Keypair.generate();
const MINT_A = 'EPjFW36vXT3Z3pJvAbYTNp3Xbw7B637vH8G2fEU3XgA';
const PUMP_MINT = 'HeLp5QiN9s7Rqfxyf9uJzT1o6u7E9Z1w8u2V3m4N5p6Q';

var mockConnection: any;
var mockVT: any;

jest.mock('ioredis', () => jest.fn().mockImplementation(() => ({
  get: jest.fn(), set: jest.fn(), incr: jest.fn(), expire: jest.fn(),
  publish: jest.fn().mockResolvedValue(1), subscribe: jest.fn(), on: jest.fn(),
  once: jest.fn().mockImplementation((event: string, cb: Function) => {
    if (event === 'ready') setTimeout(cb, 0);
  }),
  duplicate: jest.fn().mockReturnThis(), quit: jest.fn().mockResolvedValue('OK'),
  sadd: jest.fn(), srem: jest.fn(), unsubscribe: jest.fn().mockResolvedValue(1),
})));
jest.mock('fs');
jest.mock('axios');
jest.mock('../shared/keystore', () => ({ loadKeypairFromKeystore: jest.fn().mockReturnValue(SHARED_KEYPAIR) }));
jest.mock('../shared/db', () => ({
  getOpenPositions: { run: jest.fn().mockReturnValue([]) },
  updatePosition: { run: jest.fn() },
  insertAuditLog: { run: jest.fn() },
}));
jest.mock('../shared/operational-window', () => ({ isOperationalWindowActive: jest.fn().mockReturnValue(true) }));

const mockAres = {
  rateLimitedRequest: jest.fn(),
  getSolPriceUsd: jest.fn().mockResolvedValue(200),
};
jest.mock('./ares', () => mockAres);

jest.mock('@solana/web3.js', () => {
  const actual = jest.requireActual('@solana/web3.js');
  const conn = {
    getBalance: jest.fn().mockResolvedValue(1_000_000_000),
    getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: '11111111111111111111111111111111', lastValidBlockHeight: 123 }),
    sendRawTransaction: jest.fn().mockResolvedValue('sig_test'),
    confirmTransaction: jest.fn().mockResolvedValue({} as any),
    getAccountInfo: jest.fn().mockResolvedValue({ owner: new actual.PublicKey('11111111111111111111111111111111') }),
  };
  mockConnection = conn;
  const vt = {
    deserialize: jest.fn().mockImplementation(() => ({
      sign: jest.fn(),
      serialize: jest.fn().mockReturnValue(Buffer.from('signed_vt')),
    })),
  };
  mockVT = vt;
  return { ...actual, Connection: jest.fn().mockImplementation(() => conn), VersionedTransaction: vt };
});

(global as any).fetch = jest.fn();

const getDummyTxBase64 = (feePayer: PublicKey) => {
  const tx = new Transaction();
  tx.add(SystemProgram.transfer({ fromPubkey: feePayer, toPubkey: PublicKey.unique(), lamports: 1000 }));
  tx.recentBlockhash = '11111111111111111111111111111111';
  tx.feePayer = feePayer;
  return Buffer.from(tx.serialize({ verifySignatures: false })).toString('base64');
};

const defaultConfig = {
  trading: {
    tp1_multiplier: 2.0, tp2_multiplier: 5.0, sl_multiplier: 0.7,
    trailing_stop_pct: 15, time_sl_hours: 0.5, exit_bonding_curve_progress: 0,
  },
};

describe('SentinelAgent Edge Coverage', () => {
  let SentinelAgent: any;
  let agent: any;
  let mockRedis: any;

  beforeAll(() => {
    (fs.readFileSync as jest.Mock).mockReturnValue('trading:\n  tp1_multiplier: 2.0\n  tp2_multiplier: 5.0\n  sl_multiplier: 0.7\n  trailing_stop_pct: 15\n  time_sl_hours: 0.5');
    SentinelAgent = require('./sentinel').SentinelAgent;
  });

  beforeEach(() => {
    jest.clearAllMocks();
    const Redis = require('ioredis');
    mockRedis = new Redis();
    agent = new SentinelAgent({}, mockRedis);
    agent.config = JSON.parse(JSON.stringify(defaultConfig));
    agent['keypair'] = SHARED_KEYPAIR;

    mockAres.rateLimitedRequest.mockImplementation(async (fn: any) => {
      const result = await fn('https://api.jup.ag');
      if (result && result.outAmount) return result;
      return { outAmount: '1000000', swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey) };
    });
    (global.fetch as jest.Mock).mockImplementation(() => Promise.resolve({
      ok: true, status: 200, json: async () => ({ outAmount: '1000000', swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey) }),
    }));
    mockVT.deserialize.mockImplementation(() => ({
      sign: jest.fn(),
      serialize: jest.fn().mockReturnValue(Buffer.from('signed_vt')),
    }));
  });

  // L35-36: uncaughtException handler
  // L40: unhandledRejection handler
  test('covers process uncaughtException and unhandledRejection handlers (L35-36, L40)', () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation();
    process.emit('uncaughtException', new Error('test_uncaught'));
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('test_uncaught'));
    (process as any).emit('unhandledRejection', 'test_rejection_reason');
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('test_rejection_reason'));
    errorSpy.mockRestore();
  });

  // L71-75: isPaperMode() fallback paths
  test('covers isPaperMode fallback config and default (L71-75)', () => {
    const origEnv = process.env.MTUS_ENVIRONMENT;
    delete process.env.MTUS_ENVIRONMENT;

    agent.config = { ...defaultConfig, system: { environment: 'paper' } } as any;
    expect(agent['isPaperMode']()).toBe(true);

    agent.config = { ...defaultConfig, system: { environment: 'live' } } as any;
    expect(agent['isPaperMode']()).toBe(false);

    agent.config = { ...defaultConfig };
    expect(agent['isPaperMode']()).toBe(true);

    process.env.MTUS_ENVIRONMENT = origEnv;
  });

  // L93-98: init() with redis parameter + createRedisClient path
  test('covers init method with redis parameter (L93-94, L98)', async () => {
    const altRedis = { publish: jest.fn().mockResolvedValue(1) };
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    await agent.init(altRedis as any);
    expect(logSpy).toHaveBeenCalledWith('[Sentinel] Initialized');
    expect(agent['redis']).toBe(altRedis);
    logSpy.mockRestore();
  });

  test('covers init createRedisClient path (L95-98)', async () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const noRedisAgent = new SentinelAgent({});
    noRedisAgent.config = JSON.parse(JSON.stringify(defaultConfig));
    try {
      await noRedisAgent.init();
    } catch (e) {
    }
    logSpy.mockRestore();
  });

  // L107-108: loadConfig() catch block
  test('covers loadConfig error catch (L107-108)', () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    (fs.readFileSync as jest.Mock).mockImplementation(() => { throw new Error('File not found'); });
    agent['loadConfig']();
    expect(agent['config']).toBeDefined();
    expect(agent['config'].trading.tp1_multiplier).toBe(2.0);
    logSpy.mockRestore();
  });

  // L111-116: loadKeypair()
  test('covers loadKeypair (L111-116)', async () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    await agent.loadKeypair('test_passphrase');
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining('Loaded sniper wallet'));
    logSpy.mockRestore();
  });

  // L220-221: TRAILING state -> TP2 hit
  test('covers TRAILING state tp2_hit path (L220-221)', async () => {
    const sellSpy = jest.spyOn(agent, 'sellPortion').mockResolvedValue(undefined);
    const pos: any = {
      position_id: 't_tp2', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.002,
      tokens_received: 10000, state: 'TRAILING', price_buffer: [],
      entry_timestamp_utc: new Date().toISOString(),
      tp1_price: 0.002, sl_price: 0.0005, tp2_price: 0.003,
    };
    await agent.updatePositionState(pos, 0.0035);
    expect(sellSpy).toHaveBeenCalledWith(expect.objectContaining({ position_id: 't_tp2' }), 0.5, 'tp2_hit');
    sellSpy.mockRestore();
  });

  // L228: TAKE_PROFIT_2 -> CLOSED
  test('covers TAKE_PROFIT_2 to CLOSED (L228)', async () => {
    const pos: any = {
      position_id: 'tp2_state', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.002,
      tokens_received: 10000, state: 'TAKE_PROFIT_2', price_buffer: [],
      entry_timestamp_utc: new Date().toISOString(),
      tp1_price: 0.002, sl_price: 0.0005, tp2_price: 0.005,
    };
    await agent.updatePositionState(pos, 0.001);
    expect(pos.state).toBe('CLOSED');
  });

  // L303-304: Pump dust cleanup (pnl < 0.05)
  test('covers pump dust cleanup path (L303-304)', async () => {
    (axios.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('pump.fun/coins/')) {
        return Promise.resolve({ data: { virtual_sol_reserves: 100000000, virtual_token_reserves: 1000000000000000, complete: false } });
      }
      return Promise.resolve({ data: {} });
    });
    const pos: any = { position_id: 'dust_pump', mint: PUMP_MINT, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001 };
    await agent.sellPortion(pos, 1.0, 'tp1_hit');
    expect(mockRedis.publish).toHaveBeenCalled();
  });

  // L369: getSolPriceUsd catch fallback to apiVersion v1
  test('covers getSolPriceUsd catch and apiVersion fallback (L369)', async () => {
    mockAres.getSolPriceUsd.mockRejectedValue(new Error('price fetch failed'));
    process.env.MTUS_ENVIRONMENT = 'production';
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const pos: any = { position_id: 'v1_fallback', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.002 };
    (axios.get as jest.Mock).mockResolvedValue({ data: {} });
    await agent.sellPortion(pos, 1.0, 'tp2_hit');
    logSpy.mockRestore();
    process.env.MTUS_ENVIRONMENT = 'paper';
  });

  // L383-384: Jupiter dust cleanup (totalValueUsd < 0.5)
  test('covers jupiter dust cleanup aggressive slippage (L383-384)', async () => {
    jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.0000001);
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const pos: any = { position_id: 'jup_dust', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001 };
    await agent.sellPortion(pos, 1.0, 'tp1_hit');
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining('[DUST-CLEANUP]'));
    logSpy.mockRestore();
  });

  // L412-421: v2 quote flow with success
  test('covers v2 quote success path (L412-418)', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    mockAres.getSolPriceUsd.mockResolvedValue(200);
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const pos: any = { position_id: 'v2_test', mint: MINT_A, tokens_received: 1000000, entry_price_sol: 0.005, peak_price_sol: 0.005 };
    (axios.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('price/v2')) return Promise.resolve({ data: { data: { [MINT_A]: { price: 0.5 } } } });
      if (url.includes('price/v3')) return Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { usdPrice: 200 } } });
      return Promise.resolve({ data: {} });
    });
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true, status: 200, json: async () => ({ outAmount: '1000000', swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey) }),
    });
    await agent.sellPortion(pos, 1.0, 'tp2_hit');
    expect(mockConnection.sendRawTransaction).toHaveBeenCalled();
    logSpy.mockRestore();
    process.env.MTUS_ENVIRONMENT = 'paper';
  });

  // L412-421: v2 quote failure with fallback
  test('covers v2 quote failure fallback (L419-421)', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    mockAres.getSolPriceUsd.mockResolvedValue(200);
    const pos: any = { position_id: 'v2_fail', mint: MINT_A, tokens_received: 1000000, entry_price_sol: 0.005, peak_price_sol: 0.005 };
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false, status: 500, json: async () => ({}),
    });
    (axios.get as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('birdeye')) return Promise.resolve({ data: { data: { value: 2 } } });
      return Promise.resolve({ data: {} });
    });
    try {
      await agent.sellPortion(pos, 1.0, 'tp2_hit');
    } catch (e) {
    }
    process.env.MTUS_ENVIRONMENT = 'paper';
  });

  // L457-466: Insufficient SOL balance
  test('covers insufficient SOL balance abort (L457-466)', async () => {
    const origEnv = process.env.MTUS_ENVIRONMENT;
    process.env.MTUS_ENVIRONMENT = 'production';
    mockConnection.getBalance.mockResolvedValue(1000);
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const pos: any = { position_id: 'low_bal', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001 };
    await agent.sellPortion(pos, 1.0, 'tp2_hit');
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining('ABORTED'));
    logSpy.mockRestore();
    mockConnection.getBalance.mockResolvedValue(1_000_000_000);
    process.env.MTUS_ENVIRONMENT = origEnv;
  });

  // L495-497: Legacy Transaction fallback
  test('covers legacy tx fallback on VersionedTransaction failure (L495-497)', async () => {
    const origEnv = process.env.MTUS_ENVIRONMENT;
    process.env.MTUS_ENVIRONMENT = 'production';
    mockVT.deserialize.mockImplementation(() => { throw new Error('VT parse fail'); });
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const pos: any = { position_id: 'legacy_tx', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001 };
    await agent.sellPortion(pos, 1.0, 'tp2_hit');
    expect(mockConnection.sendRawTransaction).toHaveBeenCalled();
    logSpy.mockRestore();
    process.env.MTUS_ENVIRONMENT = origEnv;
  });

  // L528: sellPortion catch block
  test('covers sellPortion catch block (L528)', async () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const pos: any = { position_id: 'catch_test', mint: 'invalid!!!', tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001 };
    await agent.sellPortion(pos, 1.0, 'tp1_hit');
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining('Sell failed'));
    logSpy.mockRestore();
  });

  // L536-537: recoverPositions with no open positions
  test('covers recoverPositions with empty DB (L536-537)', async () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    await agent.recoverPositions();
    expect(console.log).toHaveBeenCalledWith('AGT-06: No open positions found in DB to recover.');
    logSpy.mockRestore();
  });

  // L565-588: handlePositionOpened
  test('covers handlePositionOpened (L565-588)', async () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const envelopeJson = JSON.stringify({
      agent_id: 'AGT-01',
      event_type: 'position_opened',
      payload: {
        mint: MINT_A,
        entryPriceSol: 0.001,
        tokensReceived: 10000,
        position_id: 'new_pos_1',
      },
      envelope_id: 'e1',
      timestamp_utc: new Date().toISOString(),
      correlation_id: 'c1',
      schema_version: '1.0.0',
    });
    await agent.handlePositionOpened(envelopeJson);
    expect(agent['positions'].has('new_pos_1')).toBe(true);
    const pos = agent['positions'].get('new_pos_1');
    expect(pos.state).toBe('OPEN');
    expect(pos.tp1_price).toBe(0.002);
    logSpy.mockRestore();
  });

  test('covers handlePositionOpened error catch (L587-588)', async () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation();
    await agent.handlePositionOpened('invalid json!!!');
    expect(console.error).toHaveBeenCalledWith(expect.stringContaining('Error handling position opened message'));
    errorSpy.mockRestore();
  });

  // L634-639: subscriber message handler
  test('covers subscriber message handler (L634-639)', async () => {
    jest.useFakeTimers();
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    let messageHandler: Function = () => {};
    mockRedis.on.mockImplementation((event: string, handler: Function) => {
      if (event === 'message') messageHandler = handler;
      return mockRedis;
    });
    mockRedis.duplicate.mockReturnValue(mockRedis);
    agent['running'] = true;
    agent.recoverPositions = jest.fn().mockResolvedValue(undefined);
    agent['positions'] = new Map();

    const runPromise = agent.run();
    await jest.advanceTimersByTimeAsync(3500);
    await Promise.resolve();

    messageHandler('mtus:channel:position_opened', JSON.stringify({
      agent_id: 'AGT-01',
      event_type: 'position_opened',
      payload: { mint: MINT_A, entryPriceSol: 0.001, tokensReceived: 10000, position_id: 'sub_pos' },
      envelope_id: 'e2', timestamp_utc: new Date().toISOString(), correlation_id: 'c2', schema_version: '1.0.0',
    }));
    await Promise.resolve();
    expect(agent['positions'].has('sub_pos')).toBe(true);

    agent['running'] = false;
    await jest.advanceTimersByTimeAsync(6000);
    await runPromise;
    logSpy.mockRestore();
    jest.useRealTimers();
  }, 10000);

  // L647-652: tearDownSubscription
  // L667: unsubscribe when inactive
  // L671-672: inactive sleep then continue
  test('covers subscription teardown and inactive loop (L647-652, L667, L671-672)', async () => {
    jest.useFakeTimers();
    const { isOperationalWindowActive } = require('../shared/operational-window');
    (isOperationalWindowActive as jest.Mock).mockReturnValue(true);

    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    agent['running'] = true;
    agent.recoverPositions = jest.fn().mockResolvedValue(undefined);
    agent['positions'] = new Map();
    mockRedis.duplicate.mockReturnValue(mockRedis);

    const runPromise = agent.run();
    await jest.advanceTimersByTimeAsync(3500);
    await Promise.resolve();
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining('Subscribed'));

    (isOperationalWindowActive as jest.Mock).mockReturnValue(false);
    await jest.advanceTimersByTimeAsync(5000);
    await Promise.resolve();
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining('Unsubscribed'));

    // After teardown, loop sees !active so it sleeps 60s then continues
    // Set running=false so loop exits when the 60s sleep resolves
    agent['running'] = false;
    await jest.advanceTimersByTimeAsync(61000);
    await Promise.resolve();
    await runPromise;
    logSpy.mockRestore();
    jest.useRealTimers();
  }, 15000);

  // L677: loop error catch - tests by making monitorPositions throw directly
  test('covers run loop error handling (L677)', async () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    // Ensure operational window is active for this test
    const { isOperationalWindowActive } = require('../shared/operational-window');
    (isOperationalWindowActive as jest.Mock).mockReturnValue(true);
    agent['running'] = true;
    // Make monitorPositions throw to trigger the loop's catch block
    agent.monitorPositions = jest.fn().mockRejectedValue(new Error('Simulated monitor error'));

    const runPromise = agent.run();
    await new Promise(r => setTimeout(r, 4000));
    await Promise.resolve();
    expect(console.log).toHaveBeenCalledWith(expect.stringContaining('[LOOP ERROR]'));

    agent['running'] = false;
    await new Promise(r => setTimeout(r, 100));
    await runPromise;
    logSpy.mockRestore();
  }, 15000);

  // Stop method coverage
  test('covers stop method', async () => {
    mockRedis.quit.mockResolvedValue('OK');
    await agent.stop();
    expect(mockRedis.quit).toHaveBeenCalled();
  });
});
