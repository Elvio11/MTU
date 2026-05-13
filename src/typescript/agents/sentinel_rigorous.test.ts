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
    rateLimitedRequest: jest.fn(),
    getSolPriceUsd: jest.fn().mockResolvedValue(200),
};
jest.mock('./ares', () => mockAres);

jest.mock('axios');
jest.mock('fs');

jest.mock('@solana/web3.js', () => {
    const actual = jest.requireActual('@solana/web3.js');
    const mockConn = {
        getBalance: jest.fn().mockResolvedValue(1_000_000_000),
        getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: '11111111111111111111111111111111', lastValidBlockHeight: 123 }),
        sendRawTransaction: jest.fn().mockResolvedValue('sig_test'),
        confirmTransaction: jest.fn().mockResolvedValue({} as any),
        getSignaturesForAddress: jest.fn().mockResolvedValue([]),
        getParsedTransaction: jest.fn().mockResolvedValue(null),
    };
    return {
        ...actual,
        Connection: jest.fn().mockImplementation(() => mockConn),
    };
});

(global as any).fetch = jest.fn();

const MINT_A = 'EPjFW36vXT3Z3pJvAbYTNp3Xbw7B637vH8G2fEU3XgA';
const PUMP_MINT = 'PUMP_MINT_ABC123_pump';

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

        jest.isolateModules(() => {
            SentinelAgent = require('./sentinel').SentinelAgent;
        });
        agent = new SentinelAgent({}, mockRedis);

        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('price/v3')) return Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { usdPrice: 200 } } });
            return Promise.resolve({ data: { data: { [MINT_A]: { price: 0.4 } } } });
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

    test('Jupiter simulated sell in paper mode', async () => {
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.002);
        const pos: any = { position_id: 'p2', mint: MINT_A, tokens_received: 10000, peak_price_sol: 0.01, entry_price_sol: 0.001 };
        await agent.sellPortion(pos, 1.0, 'tp1_hit');
        expect(mockRedis.publish).toHaveBeenCalled();
    });

    test('Jupiter production sell success', async () => {
        process.env.MTUS_ENVIRONMENT = 'production';
        let LocalSentinelAgent: any;
        jest.isolateModules(() => {
            LocalSentinelAgent = require('./sentinel').SentinelAgent;
        });
        const prodAgent = new LocalSentinelAgent({}, mockRedis);
        prodAgent['keypair'] = SHARED_KEYPAIR;
        jest.spyOn(prodAgent, 'fetchPrice').mockResolvedValue(0.002);

        const pos: any = { position_id: 'p3', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.002 };
        await prodAgent.sellPortion(pos, 1.0, 'tp2_hit');
        
        const { Connection: MockConnection } = require('@solana/web3.js');
        const connInstance = (MockConnection as jest.Mock).mock.results[0].value;
        expect(connInstance.sendRawTransaction).toHaveBeenCalled();
    });

    test('Pump.fun sell path', async () => {
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.002);
        const pos: any = { position_id: 'p_pump', mint: PUMP_MINT, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.002 };
        await agent.sellPortion(pos, 1.0, 'tp1_hit');
        expect(mockRedis.publish).toHaveBeenCalledWith('tp1_hit', expect.stringContaining('paper_pump_sell'));
    });

    test('monitorPositions logic coverage (TP/SL/Trailing Stop)', async () => {
        // Mock DB returning positions
        const { getOpenPositions } = require('../shared/db');
        const mockPositions = [
            { position_id: 'tp1', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.001, tokens_received: 10000, tp1_hit: 0, tp2_hit: 0, sl_hit: 0 },
            { position_id: 'sl', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.001, tokens_received: 10000, tp1_hit: 0, tp2_hit: 0, sl_hit: 0 },
            { position_id: 'ts', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.002, tokens_received: 10000, tp1_hit: 1, tp2_hit: 0, sl_hit: 0 },
        ];
        getOpenPositions.run.mockReturnValue(mockPositions);
        
        await agent.recoverPositions();
        
        jest.spyOn(agent, 'sellPortion').mockResolvedValue(undefined);
        
        // TP1: Price 0.0025 (2.5x)
        jest.spyOn(agent, 'fetchPrice').mockImplementation(async (mint: string) => {
            if (mint === MINT_A) return 0.0025;
            return 0.001;
        });
        
        await agent.monitorPositions();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'tp1' }), 0.5, 'tp1_hit');

        // SL: Price 0.0004 (0.4x)
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.0004);
        await agent.monitorPositions();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'sl' }), 1.0, 'stop_loss_hit');

        // Trailing Stop: Peak was 0.002, current is 0.0015 (down 25% from peak 0.002, distance is 0.2)
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.0015);
        await agent.monitorPositions();
        expect(agent.sellPortion).toHaveBeenCalledWith(expect.objectContaining({ position_id: 'ts' }), 0.5, 'trailing_stop_hit');
    });

    test('run loop executes correctly', async () => {
        jest.useFakeTimers();
        agent['dbInitialized'] = true;
        agent['running'] = true;
        jest.spyOn(agent, 'recoverPositions').mockResolvedValue(undefined);
        
        const runPromise = agent.run();
        await jest.advanceTimersByTimeAsync(3500);
        await Promise.resolve(); 
        
        agent['running'] = false;
        await jest.advanceTimersByTimeAsync(1000);
        await runPromise;
        expect(agent['recoverPositions']).toHaveBeenCalled();
        jest.useRealTimers();
    }, 10000);
});
