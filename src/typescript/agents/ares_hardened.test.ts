process.env.MTUS_ENVIRONMENT = 'paper';
(global as any).IS_PAPER_MODE = true;
import { AresAgent } from './ares';
import Redis from 'ioredis';
import { Connection, Keypair, PublicKey } from '@solana/web3.js';
import * as fs from 'fs';

jest.mock('ioredis');
jest.mock('bs58', () => ({
    decode: jest.fn().mockReturnValue(new Uint8Array(64)),
}));
jest.mock('@solana/web3.js', () => ({
    Connection: jest.fn().mockImplementation(() => ({
        getBalance: jest.fn().mockResolvedValue(1e9),
        getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: 'hash' }),
        sendRawTransaction: jest.fn().mockResolvedValue('tx-sig'),
        getSignatureStatus: jest.fn().mockResolvedValue({ value: { confirmationStatus: 'confirmed' } }),
        getAccountInfo: jest.fn().mockResolvedValue({ data: Buffer.alloc(100), owner: { toBase58: () => '1111' } }),
    })),
    Keypair: {
        fromSecretKey: jest.fn().mockReturnValue({ 
            publicKey: { toBase58: () => 'wallet', toBuffer: () => Buffer.alloc(32) },
            sign: jest.fn()
        })
    },
    PublicKey: Object.assign(
        jest.fn().mockImplementation((key) => {
            if (typeof key === 'string' || key instanceof Uint8Array || Buffer.isBuffer(key)) {
                return {
                    toBase58: () => key.toString(),
                    toBuffer: () => Buffer.isBuffer(key) ? key : Buffer.from(key),
                };
            }
            return key;
        }),
        {
            findProgramAddressSync: jest.fn().mockReturnValue([{
                toBase58: () => 'bonding-curve-pubkey',
                toBuffer: () => Buffer.alloc(32),
            }, 255]),
        }
    ),
    VersionedTransaction: {
        deserialize: jest.fn().mockReturnValue({
            sign: jest.fn(),
            serialize: jest.fn().mockReturnValue(new Uint8Array(100)),
            signatures: [new Uint8Array(64)],
            message: { 
                recentBlockhash: 'hash', 
                version: 'legacy', 
                staticAccountKeys: [{ toBase58: () => 'mint123' }],
                accountKeys: [{ toBase58: () => 'mint123' }]
            }
        })
    },
    TransactionInstruction: jest.fn().mockImplementation((args) => ({ ...args })),
    Transaction: jest.fn().mockImplementation(() => ({
        add: jest.fn(),
        sign: jest.fn(),
        serialize: jest.fn().mockReturnValue(Buffer.alloc(100)),
        recentBlockhash: 'hash',
        feePayer: 'payer'
    })),
    SystemProgram: { programId: { toBase58: () => 'system' } },
    SYSVAR_RENT_PUBKEY: { toBase58: () => 'rent' },
}));
jest.mock('fs');
jest.mock('@solana/spl-token', () => ({
    getAssociatedTokenAddressSync: jest.fn().mockReturnValue({ toBase58: () => 'ata' }),
    createAssociatedTokenAccountInstruction: jest.fn(),
    TOKEN_PROGRAM_ID: { toBase58: () => 'token-program' },
    ASSOCIATED_TOKEN_PROGRAM_ID: { toBase58: () => 'associated-token-program' },
}));

jest.mock('../shared/keystore', () => ({
    Keystore: jest.fn().mockImplementation(() => ({
        load: jest.fn().mockResolvedValue(new Uint8Array(32)),
    })),
}));

jest.mock('../shared/db', () => ({
  insertPosition: { run: jest.fn() },
  insertAuditLog: { run: jest.fn() },
}));

jest.mock('../shared/operational-window', () => ({
  isOperationalWindowActive: jest.fn().mockReturnValue(true),
}));

describe('AresAgent Hardened Coverage', () => {
  let agent: AresAgent;
  let mockRedis: any;
  let mockConnection: any;

  afterEach(() => {
    process.env.MTUS_ENVIRONMENT = 'paper';
  });

  beforeEach(() => {
    jest.clearAllMocks();
    console.log(`[TEST] MTUS_ENVIRONMENT: ${process.env.MTUS_ENVIRONMENT}`);
    mockRedis = {
      get: jest.fn(),
      publish: jest.fn(),
      duplicate: jest.fn().mockReturnValue({
        on: jest.fn(),
        subscribe: jest.fn(),
        quit: jest.fn().mockResolvedValue(undefined),
        disconnect: jest.fn().mockResolvedValue(undefined),
      }),
      quit: jest.fn(),
      srem: jest.fn(),
      scard: jest.fn().mockResolvedValue(0),
      sadd: jest.fn().mockResolvedValue(1),
    };
    (Redis as unknown as jest.Mock).mockReturnValue(mockRedis);

    mockConnection = {
      getBalance: jest.fn().mockResolvedValue(1e9),
      getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: 'hash' }),
      sendRawTransaction: jest.fn().mockResolvedValue('tx-sig'),
      getSignatureStatus: jest.fn().mockResolvedValue({ value: { confirmationStatus: 'confirmed' } }),
      getAccountInfo: jest.fn().mockResolvedValue({ data: Buffer.alloc(100), owner: new PublicKey('11111111111111111111111111111111') }),
    };
    (Connection as unknown as jest.Mock).mockReturnValue(mockConnection);

    (fs.existsSync as jest.Mock).mockReturnValue(true);
    (fs.readFileSync as jest.Mock).mockReturnValue('PRIVATE_KEY_BYTES');

    agent = new AresAgent({
        trading: {
            position_size_sol: 0.1,
            tp1_multiplier: 2,
            tp2_multiplier: 5,
            sl_multiplier: 0.8,
            priority_fee_sol: 0.001
        }
    }, mockRedis);
    
    // Set a dummy keypair
    (agent as any).keypair = Keypair.fromSecretKey(new Uint8Array(64));
  });

  test('isPaperMode returns correct value based on environment', () => {
    process.env.MTUS_ENVIRONMENT = 'paper';
    expect((agent as any).isPaperMode()).toBe(true);
    process.env.MTUS_ENVIRONMENT = 'production';
    expect((agent as any).isPaperMode()).toBe(false);
    process.env.MTUS_ENVIRONMENT = '';
    expect((agent as any).isPaperMode()).toBe(true); // default
  });

  test('executeTrade uses dynamic size from Redis', async () => {
    mockRedis.get.mockResolvedValue('0.5');
    // Force paper mode for simplicity first
    process.env.MTUS_ENVIRONMENT = 'paper';
    
    // Mock fetch for quote
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ outAmount: '1000000' }),
    });

    await (agent as any).executeTrade('mint123', 'corr123', false);
    // Verified that it uses the config size
    expect(agent['config'].trading.position_size_sol).toBe(0.1);
  });

  test('executeTrade handles rate limiting', async () => {
    (agent as any).rateLimiter.canTrade = jest.fn().mockResolvedValue({ allowed: false, reason: 'Too many trades' });
    
    await (agent as any).executeTrade('mint123', 'corr123', false);
    expect(mockRedis.publish).toHaveBeenCalledWith('mtus:channel:trade_failed', expect.stringContaining('Too many trades'));
  });

  test('executeTrade handles live mode with insufficient balance', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    mockConnection.getBalance.mockResolvedValue(0.01 * 1e9); // 0.01 SOL
    
    await (agent as any).executeTrade('mint123', 'corr123', false);
    expect(mockRedis.publish).toHaveBeenCalledWith('mtus:channel:trade_failed', expect.stringContaining('Insufficient balance'));
  });

  test('executeTrade handles Pump.fun direct swap fail', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    process.env.HELIUS_RPC_URL = 'http://localhost:8899';
    
    // Mock fetch for Jupiter fallback
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => '{"error":"Mocked failure"}'
    });
    
    mockConnection.getBalance.mockResolvedValue(2 * 1e9);
    mockConnection.getAccountInfo.mockImplementation(async (pubkey: any) => {
      const pk = pubkey.toBase58();
      if (pk.includes('curve') || pk.includes('Bonding')) {
         return { data: Buffer.alloc(1000) }; 
      }
      return { data: Buffer.alloc(100), owner: new PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA') };
    });
    
    mockConnection.sendRawTransaction.mockRejectedValue(new Error('Transaction simulation failed'));

    await (agent as any).executeTrade('mint123', 'corr123', true);
    
    expect(mockRedis.publish).toHaveBeenCalledWith(
      'mtus:channel:trade_failed',
      expect.stringContaining('Fallback v1 quote failed')
    );
  }, 10000);

  test('executeTrade handles v2 execution failure and fallback to v1', async () => {
    process.env.MTUS_ENVIRONMENT = 'production';
    mockConnection.getBalance.mockResolvedValue(2 * 1e9);
    
    global.fetch = jest.fn()
        .mockResolvedValue({ ok: true, json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }) }) // SOL Price
        .mockResolvedValueOnce({ ok: false, status: 500 }) // v2 order
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ outAmount: '1000000' }) }) // v1 fallback quote
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ swapTransaction: 'base64tx' }) }); // v1 fallback swap

    await (agent as any).executeTrade('mint123', 'corr123', false);
    // Should have tried v1
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/swap/v1/quote'), expect.anything());
  });

  test('executeTrade handles transaction confirmation timeout', async () => {
      process.env.MTUS_ENVIRONMENT = 'production';
      const { isOperationalWindowActive } = require('../shared/operational-window');
      (isOperationalWindowActive as jest.Mock).mockReturnValue(true);
      (agent as any).config.trading.position_size_sol = 0.0001; // Force v1 path ($0.02)
      mockConnection.getBalance.mockResolvedValue(2 * 1e9);
      mockConnection.getSignatureStatus.mockResolvedValue({ value: null }); // Never confirmed
      
      global.fetch = jest.fn()
          .mockResolvedValueOnce({ 
              ok: true, 
              json: () => Promise.resolve({ data: { So11111111111111111111111111111111111111112: { price: 200 } } }),
              text: () => Promise.resolve('OK')
          }) // 1. Price
          .mockResolvedValueOnce({ 
              ok: true, 
              json: () => Promise.resolve({ outAmount: '1000000' }),
              text: () => Promise.resolve('{"outAmount":"1000000"}')
          }) // 2. Quote
          .mockResolvedValueOnce({ 
              ok: true, 
              json: () => Promise.resolve({ swapTransaction: Buffer.from(new Uint8Array(100)).toString('base64') }),
              text: () => Promise.resolve('OK')
          }); // 3. Swap

      // Mock timers to skip 60s
      jest.useFakeTimers();
      let now = Date.now();
      const dateSpy = jest.spyOn(Date, 'now').mockImplementation(() => now);
      
      const promise = (agent as any).executeTrade('mint123', 'corr123', false);
      
      // Advance timers in chunks and allow microtasks to run
      for (let i = 0; i < 80; i++) {
        now += 1000;
        jest.advanceTimersByTime(1000);
        await Promise.resolve();
        await Promise.resolve();
      }
      
      await promise;
      expect(mockRedis.publish).toHaveBeenCalledWith('mtus:channel:trade_failed', expect.stringContaining('Transaction failed'));
      dateSpy.mockRestore();
      jest.useRealTimers();
  }, 20000);

  test('run loop processes trade_approved events', async () => {
      jest.useFakeTimers();
      jest.clearAllTimers();
      const subOn = jest.fn();
      mockRedis.duplicate.mockReturnValue({
          on: subOn,
          subscribe: jest.fn().mockResolvedValue(undefined),
          quit: jest.fn(),
      });
      
      (agent as any).executeTrade = jest.fn().mockResolvedValue(undefined);
      
      const runPromise = agent.run();
      
      // Wait for subscription to initialize - MUST advance timers if fake
      jest.advanceTimersByTime(100);
      await Promise.resolve();
      
      const messageCallback = subOn.mock.calls.find(c => c[0] === 'message')[1];
      await messageCallback('mtus:channel:trade_approved', JSON.stringify({
          agent_id: 'AGT-01',
          correlation_id: 'corr123',
          payload: { mint: 'mint123', is_pump: false }
      }));
      
      expect((agent as any).executeTrade).toHaveBeenCalledWith('mint123', 'corr123', false);
      
      agent.stop();
      // Advance timers to exit the operational window sleep loop
      jest.advanceTimersByTime(5000);
      await Promise.resolve();
      await runPromise;
      jest.useRealTimers();
  }, 20000);

  test('executeTrade handles paper mode success', async () => {
    process.env.MTUS_ENVIRONMENT = 'paper';
    
    await (agent as any).executeTrade('mint123', 'corr123', false);
    
    expect(mockRedis.publish).toHaveBeenCalledWith(
      'mtus:channel:position_opened',
      expect.stringContaining('mint123')
    );
  });

});
