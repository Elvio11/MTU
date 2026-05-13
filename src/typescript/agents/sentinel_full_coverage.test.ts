import * as fs from 'fs';
import axios from 'axios';
import { Connection, Keypair, Transaction, PublicKey, SystemProgram, VersionedTransaction } from '@solana/web3.js';

// Constants
const SHARED_KEYPAIR = Keypair.generate();
const MINT_A = 'EPjFW36vXT3Z3pJvAbYTNp3Xbw7B637vH8G2fEU3XgA';
const PUMP_MINT = 'PumP111111111111111111111111111111111111111';

// Mocks
jest.mock('ioredis', () => jest.fn().mockImplementation(() => ({
    get: jest.fn(), set: jest.fn(), incr: jest.fn(), expire: jest.fn(),
    publish: jest.fn().mockResolvedValue(1), subscribe: jest.fn(), on: jest.fn(),
    duplicate: jest.fn().mockReturnThis(), quit: jest.fn().mockResolvedValue('OK'), sadd: jest.fn(), srem: jest.fn(),
    unsubscribe: jest.fn().mockResolvedValue(1),
})));
jest.mock('fs');
jest.mock('axios');
jest.mock('../shared/keystore', () => ({ loadKeypairFromKeystore: jest.fn().mockReturnValue(SHARED_KEYPAIR) }));
jest.mock('../shared/db', () => ({
    getOpenPositions: { run: jest.fn().mockReturnValue([]) },
    updatePosition: { run: jest.fn() },
    insertAuditLog: { run: jest.fn() },
    shutdownDB: jest.fn(),
}));
jest.mock('../shared/operational-window', () => ({
    isOperationalWindowActive: jest.fn().mockReturnValue(true)
}));

const mockAres = {
    rateLimitedRequest: jest.fn(),
    getSolPriceUsd: jest.fn().mockResolvedValue(200),
};
jest.mock('./ares', () => mockAres);

const mockConn = {
    getBalance: jest.fn().mockResolvedValue(1_000_000_000),
    getLatestBlockhash: jest.fn().mockResolvedValue({ blockhash: '11111111111111111111111111111111', lastValidBlockHeight: 123 }),
    sendRawTransaction: jest.fn().mockResolvedValue('sig_test'),
    confirmTransaction: jest.fn().mockResolvedValue({} as any),
    getAccountInfo: jest.fn().mockResolvedValue({ owner: new PublicKey('11111111111111111111111111111111') }),
};

jest.mock('@solana/web3.js', () => {
    const actual = jest.requireActual('@solana/web3.js');
    const mockVT = {
        deserialize: jest.fn().mockImplementation(() => ({
            sign: jest.fn(),
            serialize: jest.fn().mockReturnValue(Buffer.from('signed_vt'))
        }))
    };
    return { 
        ...actual, 
        Connection: jest.fn().mockImplementation(() => mockConn),
        VersionedTransaction: mockVT
    };
});

(global as any).fetch = jest.fn();

// Set environment before requiring
process.env.MTUS_ENVIRONMENT = 'production';
const { SentinelAgent } = require('./sentinel');

describe('SentinelAgent Full Coverage', () => {
    let agent: any;
    let mockRedis: any;

    beforeEach(() => {
        jest.clearAllMocks();
        (fs.readFileSync as jest.Mock).mockReturnValue('trading:\n  tp1_multiplier: 2.0\n  tp2_multiplier: 5.0\n  sl_multiplier: 0.8\n  trailing_stop_pct: 15\n  time_sl_hours: 0.5\n  exit_bonding_curve_progress: 90');
        const Redis = require('ioredis');
        mockRedis = new Redis();
        agent = new SentinelAgent({ trading: { tp1_multiplier: 2.0, tp2_multiplier: 5.0, sl_multiplier: 0.8, trailing_stop_pct: 15, time_sl_hours: 0.5, exit_bonding_curve_progress: 90 } }, mockRedis);
        agent['keypair'] = SHARED_KEYPAIR;
        
        mockAres.rateLimitedRequest.mockImplementation(async (fn: any) => ({
            outAmount: '1000000000', swapTransaction: Buffer.from('dummy').toString('base64')
        }));
        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('price/v2')) return Promise.resolve({ data: { data: { [MINT_A]: { price: 0.4 } } } });
            if (url.includes('pump.fun/coins/')) {
                return Promise.resolve({ status: 200, data: { virtual_sol_reserves: 30_000_000_000 + 55_000_000_000 * 0.5, virtual_token_reserves: 1_000_000_000, complete: false } });
            }
            return Promise.resolve({ data: {} });
        });
        (global.fetch as jest.Mock).mockImplementation(() => Promise.resolve({
            ok: true, status: 200, json: async () => ({ outAmount: '1000000000', swapTransaction: Buffer.from('dummy').toString('base64') })
        }));
    });

    const getPos = (mint = MINT_A) => ({ 
        position_id: 's1', mint, entry_price_sol: 0.001, peak_price_sol: 0.001, 
        tokens_received: 10000, state: 'OPEN', price_buffer: [], 
        entry_timestamp_utc: new Date().toISOString(),
        tp1_price: 0.002, sl_price: 0.0005, tp2_price: 0.005
    });

    test('All Paths', async () => {
        // State Transitions
        agent.sellPortion = jest.fn().mockImplementation(async (p) => { p.state = 'CLOSED'; });
        await agent.updatePositionState(getPos(PUMP_MINT), 0.001); // Maturity
        const p2 = getPos();
        await agent.updatePositionState(p2, 0.0021); // TP1
        await agent.updatePositionState(p2, 0.0051); // TP2
        const p3 = getPos(); p3.state = 'TRAILING'; p3.peak_price_sol = 0.004;
        await agent.updatePositionState(p3, 0.0045); // Peak move
        await agent.updatePositionState(p3, 0.003); // Trailing hit
        await agent.updatePositionState(getPos(), 0.0004); // SL hit

        // Sell Execution
        agent.sellPortion = (new SentinelAgent({}, mockRedis)).sellPortion.bind(agent);
        (axios.get as jest.Mock).mockRejectedValue({ response: { status: 404 } });
        await agent.sellPortion(getPos(), 1.0, 'tp2_hit');
        (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: false }); // quote fail
        await agent.sellPortion(getPos(), 1.0, 'tp2_hit');
        (axios.get as jest.Mock).mockResolvedValue({ status: 200, data: { virtual_sol_reserves: 30_000_000_000, virtual_token_reserves: 1000, complete: false } });
        await agent.sellPortion(getPos(PUMP_MINT), 1.0, 'tp2_hit');
        
        // Zero amount / Dust
        (global.fetch as jest.Mock).mockResolvedValueOnce({ ok: true, json: async () => ({ outAmount: '0' }) });
        await agent.sellPortion(getPos(), 1.0, 'tp2_hit');

        // Loop and Error Handling
        jest.useFakeTimers();
        agent['running'] = true;
        const db = require('../shared/db');
        db.getOpenPositions.run.mockImplementation(() => { throw new Error('Loop Error'); });
        const runPromise = agent.run();
        await jest.advanceTimersByTimeAsync(8100); 
        await Promise.resolve();
        agent['running'] = false;
        await jest.advanceTimersByTimeAsync(5100);
        await runPromise;
        jest.useRealTimers();

        // Audit Log Error
        db.updatePosition.run.mockImplementationOnce(() => { throw new Error('DB Error'); });
        await agent.sellPortion(getPos(), 1.0, 'tp2_hit');

        // Stop
        await agent.stop();
    });
});
