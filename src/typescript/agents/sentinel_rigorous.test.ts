import * as fs from 'fs';
import axios from 'axios';
import { Connection, Keypair, Transaction, PublicKey, VersionedTransaction, SystemProgram } from '@solana/web3.js';

const SHARED_KEYPAIR = Keypair.generate();

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
    rateLimitedRequest: jest.fn().mockImplementation((fn) => fn('https://api.jup.ag')),
    getSolPriceUsd: jest.fn().mockResolvedValue(200),
};
jest.mock('./ares', () => mockAres);

jest.mock('axios', () => ({
    get: jest.fn().mockResolvedValue({ data: { outAmount: '1000000', priceImpactPct: '0.1' } }),
    post: jest.fn().mockResolvedValue({ data: { swapTransaction: Buffer.alloc(64).toString('base64') } }),
}));
jest.mock('fs');
jest.mock('child_process', () => ({
    execSync: jest.fn().mockImplementation((cmd: string) => {
        if (cmd.includes('jup spot swap')) {
            return Buffer.from(JSON.stringify({ signature: 'mock_sell_signature' }));
        }
        return Buffer.from('ok');
    }),
}));

jest.mock('@solana/web3.js', () => {
    const actual = jest.requireActual('@solana/web3.js');
    const mockConn = {
        getBalance: jest.fn().mockResolvedValue(1_000_000_000),
        getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: '11111111111111111111111111111111', lastValidBlockHeight: 123 }),
        sendRawTransaction: jest.fn().mockResolvedValue('sig_test'),
        confirmTransaction: jest.fn().mockResolvedValue({ value: { err: null } }),
        getSignaturesForAddress: jest.fn().mockResolvedValue([]),
        getParsedTransaction: jest.fn().mockResolvedValue(null),
        getAccountInfo: jest.fn().mockResolvedValue({ data: Buffer.alloc(165) }),
    };
    
    function MockVersionedTransaction() {}
    MockVersionedTransaction.deserialize = jest.fn().mockReturnValue({
        sign: jest.fn(),
        serialize: jest.fn().mockReturnValue(Buffer.from('test')),
    });

    return {
        ...actual,
        Connection: jest.fn().mockImplementation(() => mockConn),
        VersionedTransaction: MockVersionedTransaction,
    };
});

(global as any).fetch = jest.fn();

const MINT_A = 'EPjFW36vXT3Z3pJvAbYTNp3Xbw7B637vH8G2fEU3XgA';
const PUMP_MINT = 'HeLp5QiN9s7Rqfxyf9uJzT1o6u7E9Z1w8u2V3m4N5p6Q'; // Valid-looking base58

describe('SentinelAgent Rigorous Coverage', () => {
    let SentinelAgent: any;
    let agent: any;
    let mockRedis: any;

    beforeEach(() => {
        jest.clearAllMocks();
        const Redis = require('ioredis');
        mockRedis = new Redis();
        
        process.env.MTUS_ENVIRONMENT = 'paper';
        (fs.readFileSync as jest.Mock).mockReturnValue('trading:\n  tp1_multiplier: 2.0\n  tp2_multiplier: 3.0\n  sl_multiplier: 0.5\n  trailing_stop_activation: 1.5\n  trailing_stop_distance: 0.2');
        
        mockAres.rateLimitedRequest.mockImplementation(async (fn: any) => {
            return { 
                outAmount: '1000000', 
                swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey)
            };
        });

        const { SentinelAgent: SA } = require('./sentinel');
        SentinelAgent = SA;
        agent = new SentinelAgent({}, mockRedis);

        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('price/v3')) return Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { usdPrice: 200 } } });
            if (url.includes('pump.fun/coins/')) {
                if (url.includes(PUMP_MINT)) {
                    return Promise.resolve({ data: { virtual_sol_reserves: 40000000000, complete: false, virtual_token_reserves: 1000000000000 } });
                }
                return Promise.reject({ response: { status: 404 } });
            }
            return Promise.resolve({ data: { data: { [MINT_A]: { price: 0.4 }, [PUMP_MINT]: { price: 0.5 } } } });
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

        // Mock Connection
        const { Connection } = require('@solana/web3.js');
        Connection.prototype.getAccountInfo = jest.fn().mockResolvedValue({ data: Buffer.alloc(165) });
        Connection.prototype.sendRawTransaction = jest.fn().mockResolvedValue('test_sig');
        Connection.prototype.getLatestBlockhash = jest.fn().mockResolvedValue({ blockhash: 'abc', lastValidBlockHeight: 123 });
        Connection.prototype.confirmTransaction = jest.fn().mockResolvedValue({ value: { err: null } });
    });

    test('Jupiter simulated sell in paper mode', async () => {
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.002);
        const pos: any = { position_id: 'p2', mint: MINT_A, tokens_received: 10000, peak_price_sol: 0.01, entry_price_sol: 0.001 };
        await agent.sellPortion(pos, 1.0, 'tp1_hit');
        expect(mockRedis.publish).toHaveBeenCalled();
    });

    test('Jupiter production sell success', async () => {
        process.env.MTUS_ENVIRONMENT = 'production';
        const prodAgent = new SentinelAgent('prod-test', mockRedis);
        prodAgent['keypair'] = SHARED_KEYPAIR;
        jest.spyOn(prodAgent, 'fetchPrice').mockResolvedValue(0.002);

        const pos: any = { position_id: 'p3', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.002, state: 'OPEN' };
        await prodAgent.sellPortion(pos, 1.0, 'tp2_hit');
        
        const { execSync } = require('child_process');
        expect(execSync).toHaveBeenCalledWith(expect.stringContaining('jup spot swap'));
    });

    test('Pump.fun sell path', async () => {
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.002);
        const pos: any = { position_id: 'p_pump', mint: PUMP_MINT, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.002 };
        await agent.sellPortion(pos, 1.0, 'tp1_hit');
        expect(mockRedis.publish).toHaveBeenCalledWith('mtus:channel:tp1_hit', expect.stringContaining('paper_pump_sell'));
    });

    test('monitorPositions logic coverage (TP/SL/Trailing Stop)', async () => {
        // Mock DB returning positions
        const db = require('../shared/db');
        const mockPositions = [
            { position_id: 'tp1', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.001, tokens_received: 10000, tp1_hit: 0, tp2_hit: 0, sl_hit: 0, state: 'OPEN', tp1_price: 0.002, sl_price: 0.0007, trailing_stop_distance: 0.2 },
            { position_id: 'sl', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.001, tokens_received: 10000, tp1_hit: 0, tp2_hit: 0, sl_hit: 0, state: 'OPEN', tp1_price: 0.01, sl_price: 0.0007, trailing_stop_distance: 0.2 }, // High TP1
            { position_id: 'ts', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.002, tokens_received: 10000, tp1_hit: 1, tp2_hit: 0, sl_hit: 0, state: 'TAKE_PROFIT_1', tp1_price: 0.002, sl_price: 0.0007, trailing_stop_distance: 0.2 },
        ];
        db.getOpenPositions.run.mockReturnValue(mockPositions);
        
        await agent.recoverPositions();
        
        jest.spyOn(agent, 'sellPortion').mockResolvedValue(undefined);
        
        // TP1: Price 0.0025 (2.5x)
        const fetchPricesSpy = jest.spyOn(agent, 'fetchPricesBatch').mockResolvedValue({
            [MINT_A]: 0.0025
        });
        
        await agent.monitorPositions();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'tp1' }), 0.5, 'tp1_hit');

        // SL: Price 0.0004 (0.4x)
        fetchPricesSpy.mockResolvedValue({
            [MINT_A]: 0.0004
        });
        await agent.monitorPositions();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'sl' }), 1.0, 'stop_loss_hit');

        // Trailing Stop: Position 'ts' was already in TAKE_PROFIT_1. 
        // Peak was 0.002, current is 0.0015 (down 25% from peak, distance 0.2 means exit at 0.0016)
        fetchPricesSpy.mockResolvedValue({
            [MINT_A]: 0.0015
        });
        await agent.monitorPositions();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'ts' }), 0.5, 'trailing_stop_hit');
    });

    test('run loop executes correctly', async () => {
        jest.useFakeTimers();
        agent['dbInitialized'] = true;
        agent['running'] = true;
        jest.spyOn(agent, 'recoverPositions').mockResolvedValue(undefined);
        
        const runPromise = agent.run();
        // Wait for the initial 3s delay in agent.run()
        await jest.advanceTimersByTimeAsync(3100);
        await Promise.resolve(); 
        
        // Advance for one loop iteration (5s)
        await jest.advanceTimersByTimeAsync(5000);
        await Promise.resolve();
        
        agent['running'] = false;
        await jest.advanceTimersByTimeAsync(5000); // Wait for the final polling sleep to finish
        await runPromise;
        expect(agent['recoverPositions']).toHaveBeenCalled();
        jest.useRealTimers();
    }, 10000);

    test('exitPositionPump logic', async () => {
        const { SentinelAgent } = require('./sentinel');
        const agent = new SentinelAgent({ trading: { stop_loss_pct: 10 } }, mockRedis);
        agent.keypair = SHARED_KEYPAIR;
        
        const mockPos = {
            position_id: 'pos1',
            mint: PUMP_MINT,
            tokens_received: 1000000,
            entry_price_sol: 0.001,
            peak_price_sol: 0.002
        };
        
        // @ts-ignore
        await agent['sellPortion'](mockPos, 1.0, 'tp1_hit');
        expect(mockRedis.publish).toHaveBeenCalled();
    });
});
