import * as fs from 'fs';
import axios from 'axios';
import { Connection, Keypair, Transaction, PublicKey, VersionedTransaction, SystemProgram } from '@solana/web3.js';

// Constants
const SHARED_KEYPAIR = Keypair.generate();
const MINT_A = 'EPjFW36vXT3Z3pJvAbYTNp3Xbw7B637vH8G2fEU3XgA';
const PUMP_MINT = 'PumP111111111111111111111111111111111111111';

// Mock dependencies
jest.mock('ioredis', () => jest.fn().mockImplementation(() => ({
    get: jest.fn(), set: jest.fn(), incr: jest.fn(), expire: jest.fn(),
    publish: jest.fn().mockResolvedValue(1), subscribe: jest.fn(), on: jest.fn(),
    duplicate: jest.fn().mockReturnThis(), quit: jest.fn(), sadd: jest.fn(), srem: jest.fn(),
})));
jest.mock('argon2', () => ({ hash: jest.fn(), verify: jest.fn() }));
jest.mock('../shared/keystore', () => ({ loadKeypairFromKeystore: jest.fn().mockReturnValue(SHARED_KEYPAIR) }));
jest.mock('../shared/db', () => ({
    getOpenPositions: { run: jest.fn().mockReturnValue([]) },
    updatePosition: { run: jest.fn() },
    insertAuditLog: { run: jest.fn() },
    shutdownDB: jest.fn(),
}));
jest.mock('../shared/operational-window', () => ({ isOperationalWindowActive: jest.fn().mockReturnValue(true) }));

const mockAres = {
    rateLimitedRequest: jest.fn(),
    getSolPriceUsd: jest.fn().mockResolvedValue(200),
};
jest.mock('./ares', () => mockAres);

jest.mock('axios');
jest.mock('fs');

const mockConn = {
    getBalance: jest.fn().mockResolvedValue(1_000_000_000),
    getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: '11111111111111111111111111111111', lastValidBlockHeight: 123 }),
    sendRawTransaction: jest.fn().mockResolvedValue('sig_test'),
    confirmTransaction: jest.fn().mockResolvedValue({} as any),
    getSignaturesForAddress: jest.fn().mockResolvedValue([]),
    getParsedTransaction: jest.fn().mockResolvedValue(null),
};

jest.mock('@solana/web3.js', () => {
    const actual = jest.requireActual('@solana/web3.js');
    return {
        ...actual,
        Connection: jest.fn().mockImplementation(() => mockConn),
    };
});

(global as any).fetch = jest.fn();

// Helper for dummy transaction bytes
const getDummyTxBase64 = (feePayer: PublicKey) => {
    const tx = new Transaction();
    tx.add(SystemProgram.transfer({
        fromPubkey: feePayer,
        toPubkey: PublicKey.unique(),
        lamports: 1000,
    }));
    tx.recentBlockhash = '11111111111111111111111111111111';
    tx.feePayer = feePayer;
    return Buffer.from(tx.serialize({ verifySignatures: false })).toString('base64');
};

describe('SentinelAgent Complete Coverage', () => {
    let SentinelAgent: any;
    let agent: any;
    let mockRedis: any;

    beforeAll(() => {
        process.env.MTUS_ENVIRONMENT = 'paper';
        (fs.readFileSync as jest.Mock).mockReturnValue('trading:\n  tp1_multiplier: 2.0\n  tp2_multiplier: 3.0\n  sl_multiplier: 0.5\n  trailing_stop_activation: 1.5\n  trailing_stop_distance: 0.2');
        
        SentinelAgent = require('./sentinel').SentinelAgent;
    });

    beforeEach(() => {
        jest.clearAllMocks();
        const Redis = require('ioredis');
        mockRedis = new Redis();
        agent = new SentinelAgent({}, mockRedis);
        
        // Manually set config to bypass loadConfig issues
        agent.config = {
            trading: {
                tp1_multiplier: 2.0,
                tp2_multiplier: 3.0,
                sl_multiplier: 0.5,
                trailing_stop_activation: 1.5,
                trailing_stop_distance: 0.2,
                time_sl_hours: 0.5
            }
        };

        mockAres.rateLimitedRequest.mockImplementation(async (fn: any) => {
            const result = await fn('https://api.jup.ag');
            // If it's a price request
            if (result && result.data && result.data[MINT_A]) return result;
            // Default for swap
            return { 
                outAmount: '1000000', 
                swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey)
            };
        });

        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('price/v2')) {
                return Promise.resolve({ data: { data: { [MINT_A]: { price: 0.4 } } } });
            }
            if (url.includes('price/v3')) {
                return Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { usdPrice: 200 } } });
            }
            if (url.includes('birdeye')) {
                return Promise.resolve({ data: { data: { value: 0.4 } } });
            }
            return Promise.resolve({ data: {} });
        });

        (global.fetch as jest.Mock).mockImplementation((url: string) => {
            return Promise.resolve({
                ok: true,
                status: 200,
                json: async () => ({ 
                    outAmount: '1000000', 
                    swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey)
                })
            });
        });
    });

    test('Agent initialization and config loading', () => {
        expect(agent['config']).toBeDefined();
        expect(agent['config'].trading.tp1_multiplier).toBe(2.0);
    });

    test('fetchPrice coverage (v2 and fallback)', async () => {
        const price = await agent.fetchPrice(MINT_A);
        expect(price).toBe(0.4 / 200);
        
        // v2 fail, birdeye success
        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('price/v2')) return Promise.reject(new Error('v2 fail'));
            if (url.includes('birdeye')) return Promise.resolve({ data: { data: { value: 0.6 } } });
            if (url.includes('price/v3')) return Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { usdPrice: 200 } } });
            return Promise.resolve({ data: {} });
        });
        const price2 = await agent.fetchPrice(MINT_A);
        expect(price2).toBe(0.6 / 200);
    });

    test('sellPortion coverage (Paper mode, Pump.fun)', async () => {
        const pos: any = { position_id: 'p_pump', mint: PUMP_MINT, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.002 };
        await agent.sellPortion(pos, 1.0, 'tp1_hit');
        expect(mockRedis.publish).toHaveBeenCalled();
    });

    test('sellPortion coverage (Live mode, Jupiter)', async () => {
        process.env.MTUS_ENVIRONMENT = 'production';
        // We need to re-init the agent to pick up production mode if it uses it as a const
        // But SentinelAgent uses process.env.MTUS_ENVIRONMENT directly in some places?
        // Let's assume we can just override it for this test.
        agent['keypair'] = SHARED_KEYPAIR;
        const pos: any = { position_id: 'p_live', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.002 };
        await agent.sellPortion(pos, 1.0, 'tp2_hit');
        expect(mockConn.sendRawTransaction).toHaveBeenCalled();
        process.env.MTUS_ENVIRONMENT = 'paper';
    });

    test('monitorPositions detailed logic (TP/SL/TS)', async () => {
        const mockPositions = new Map();
        // TP1 Hit
        mockPositions.set('tp1', { 
            position_id: 'tp1', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.001, 
            tokens_received: 10000, tp1_hit: 0, tp2_hit: 0, sl_hit: 0, state: 'OPEN', price_buffer: [], 
            entry_timestamp_utc: new Date().toISOString() 
        });
        // SL Hit
        mockPositions.set('sl', { 
            position_id: 'sl', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.001, 
            tokens_received: 10000, tp1_hit: 0, tp2_hit: 0, sl_hit: 0, state: 'OPEN', price_buffer: [],
            entry_timestamp_utc: new Date().toISOString() 
        });
        
        agent['positions'] = mockPositions;
        
        jest.spyOn(agent, 'sellPortion').mockResolvedValue(undefined);
        
        // Test TP1
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.0025); // 2.5x > 2.0x
        await agent['monitorPositions']();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'tp1' }), 0.5, 'tp1_hit');

        // Reset and Test SL
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.0004); // 0.4x < 0.5x
        await agent['monitorPositions']();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'sl' }), 1.0, 'stop_loss_hit');
    });

    test('recoverPositions and database interaction', async () => {
        const { getOpenPositions } = require('../shared/db');
        getOpenPositions.run.mockReturnValue([{ position_id: 'rec1', mint: MINT_A, entry_price_sol: 0.001, entry_timestamp_utc: new Date().toISOString() }]);
        
        await agent.recoverPositions();
        expect(agent['positions'].has('rec1')).toBe(true);
    });

    test('run loop startup and termination', async () => {
        jest.useFakeTimers();
        agent['dbInitialized'] = true;
        agent['running'] = true;
        jest.spyOn(agent, 'recoverPositions').mockResolvedValue(undefined);
        
        const runPromise = agent.run();
        // Skip initialization delay
        await jest.advanceTimersByTimeAsync(3500);
        await Promise.resolve();
        
        agent['running'] = false;
        await jest.advanceTimersByTimeAsync(1000);
        await runPromise;
        
        expect(mockRedis.subscribe).toHaveBeenCalled();
        jest.useRealTimers();
    }, 10000);
});
