import * as fs from 'fs';
import axios from 'axios';
import { Connection, Keypair, Transaction, PublicKey, SystemProgram } from '@solana/web3.js';

// Constants
const SHARED_KEYPAIR = Keypair.generate();
const MINT_A = 'EPjFW36vXT3Z3pJvAbYTNp3Xbw7B637vH8G2fEU3XgA';
const PUMP_MINT = 'PumP111111111111111111111111111111111111111';

// Mocks
jest.mock('ioredis', () => jest.fn().mockImplementation(() => ({
    get: jest.fn(), set: jest.fn(), incr: jest.fn(), expire: jest.fn(),
    publish: jest.fn().mockResolvedValue(1), subscribe: jest.fn(), on: jest.fn(),
    duplicate: jest.fn().mockReturnThis(), quit: jest.fn(), sadd: jest.fn(), srem: jest.fn(),
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
jest.mock('../shared/operational-window', () => ({ isOperationalWindowActive: jest.fn().mockReturnValue(true) }));

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
};
jest.mock('@solana/web3.js', () => {
    const actual = jest.requireActual('@solana/web3.js');
    return { ...actual, Connection: jest.fn().mockImplementation(() => mockConn) };
});

(global as any).fetch = jest.fn();

const getDummyTxBase64 = (feePayer: PublicKey) => {
    const tx = new Transaction();
    tx.add(SystemProgram.transfer({ fromPubkey: feePayer, toPubkey: PublicKey.unique(), lamports: 1000 }));
    tx.recentBlockhash = '11111111111111111111111111111111';
    tx.feePayer = feePayer;
    return Buffer.from(tx.serialize({ verifySignatures: false })).toString('base64');
};

describe('SentinelAgent Paper Coverage', () => {
    let SentinelAgent: any;
    let agent: any;
    let mockRedis: any;

    beforeAll(() => {
        process.env.MTUS_ENVIRONMENT = 'paper';
        (fs.readFileSync as jest.Mock).mockReturnValue('trading:\n  tp1_multiplier: 2.0\n  tp2_multiplier: 3.0\n  sl_multiplier: 0.5\n  trailing_stop_activation: 1.5\n  trailing_stop_distance: 0.2\n  exit_bonding_curve_progress: 90');
        SentinelAgent = require('./sentinel').SentinelAgent;
    });

    beforeEach(() => {
        jest.clearAllMocks();
        const Redis = require('ioredis');
        mockRedis = new Redis();
        agent = new SentinelAgent({}, mockRedis);
        agent.config = { 
            trading: { 
                tp1_multiplier: 2.0, 
                tp2_multiplier: 3.0, 
                sl_multiplier: 0.5, 
                trailing_stop_activation: 1.5, 
                trailing_stop_distance: 0.2,
                trailing_stop_pct: 15,
                exit_bonding_curve_progress: 90,
                time_sl_hours: 0.5
            } 
        };
        
        mockAres.rateLimitedRequest.mockImplementation(async (fn: any) => ({
            outAmount: '1000000', swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey)
        }));
        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('price/v2')) return Promise.resolve({ data: { data: { [MINT_A]: { price: 0.4 } } } });
            if (url.includes('price/v3')) return Promise.resolve({ data: { 'So11111111111111111111111111111111111111112': { usdPrice: 200 } } });
            if (url.includes('pump.fun/coins/')) return Promise.resolve({ data: { virtual_sol_reserves: 30_000_000_000, complete: false } }); // 0% progress
            return Promise.resolve({ data: {} });
        });
        (global.fetch as jest.Mock).mockImplementation(() => Promise.resolve({
            ok: true, status: 200, json: async () => ({ outAmount: '1000000', swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey) })
        }));
    });

    test('Paper mode sellPortion coverage', async () => {
        // v1 path (dust cleanup trigger)
        const pos: any = { position_id: 'p1', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001, state: 'OPEN', entry_timestamp_utc: new Date().toISOString() };
        jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.0001); 
        await agent.sellPortion(pos, 1.0, 'tp1_hit');
        expect(mockRedis.publish).toHaveBeenCalled();

        // Pump path
        const posPump: any = { position_id: 'p2', mint: PUMP_MINT, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001, state: 'OPEN', entry_timestamp_utc: new Date().toISOString() };
        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('pump.fun/coins/')) return Promise.resolve({ data: { virtual_sol_reserves: 40_000_000_000, complete: false } });
            return Promise.resolve({ data: {} });
        });
        await agent.sellPortion(posPump, 1.0, 'tp2_hit');
        expect(mockRedis.publish).toHaveBeenCalledWith('mtus:channel:tp2_hit', expect.stringContaining('paper_pump_sell'));
    });

    test('updatePositionState detailed coverage', async () => {
        const pos: any = { 
            position_id: 'm1', mint: MINT_A, entry_price_sol: 0.001, peak_price_sol: 0.001, 
            tokens_received: 10000, tp1_hit: 0, tp2_hit: 0, sl_hit: 0, state: 'OPEN', 
            price_buffer: [], entry_timestamp_utc: new Date().toISOString(),
            tp1_price: 0.002, sl_price: 0.0005, tp2_price: 0.003
        };
        
        const sellSpy = jest.spyOn(agent, 'sellPortion').mockResolvedValue(undefined);
        
        // 1. Time-based stop loss
        const oldDate = new Date();
        oldDate.setHours(oldDate.getHours() - 1);
        pos.entry_timestamp_utc = oldDate.toISOString();
        await agent.updatePositionState(pos, 0.001);
        expect(sellSpy).toHaveBeenCalledWith(expect.anything(), 1.0, 'time_sl_hit');
        sellSpy.mockClear();
        
        // 2. Maturity exit
        pos.state = 'OPEN';
        pos.entry_timestamp_utc = new Date().toISOString();
        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('pump.fun/coins/')) return Promise.resolve({ data: { virtual_sol_reserves: 80_000_000_000, complete: false } });
            return Promise.resolve({ data: {} });
        });
        await agent.updatePositionState(pos, 0.001);
        expect(sellSpy).toHaveBeenCalledWith(expect.anything(), 1.0, 'tp2_hit');
        sellSpy.mockClear();

        // 3. TP1 Hit
        pos.state = 'OPEN';
        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('pump.fun/coins/')) return Promise.resolve({ data: { virtual_sol_reserves: 30_000_000_000, complete: false } });
            return Promise.resolve({ data: {} });
        });
        await agent.updatePositionState(pos, 0.0021);
        expect(sellSpy).toHaveBeenCalledWith(expect.anything(), 0.5, 'tp1_hit');
        expect(pos.state).toBe('TAKE_PROFIT_1');
        sellSpy.mockClear();

        // 4. Trailing Stop Hit (Peak 0.0021, trailing 15% -> 0.001785)
        pos.peak_price_sol = 0.0021;
        await agent.updatePositionState(pos, 0.0017);
        expect(sellSpy).toHaveBeenCalledWith(expect.anything(), 0.5, 'trailing_stop_hit');
        sellSpy.mockClear();

        // 5. TP2 Hit
        pos.state = 'TAKE_PROFIT_1';
        pos.peak_price_sol = 0.0021;
        await agent.updatePositionState(pos, 0.0031);
        expect(sellSpy).toHaveBeenCalledWith(expect.anything(), 0.5, 'tp2_hit');
        sellSpy.mockClear();

        // 6. Stop Loss Hit
        pos.state = 'OPEN';
        await agent.updatePositionState(pos, 0.0004);
        expect(sellSpy).toHaveBeenCalledWith(expect.anything(), 1.0, 'stop_loss_hit');
    });

    test('run loop startup and termination', async () => {
        jest.useFakeTimers();
        let now = Date.now();
        jest.spyOn(Date, 'now').mockImplementation(() => now);
        
        agent['dbInitialized'] = true;
        agent['running'] = true;
        // Ensure methods called in loop are mocked
        agent.recoverPositions = jest.fn().mockResolvedValue(undefined);
        agent.fetchPrice = jest.fn().mockResolvedValue(0);
        
        const runPromise = agent.run();
        
        // Wait for 3s startup sleep
        for (let i = 0; i < 8; i++) {
            now += 500;
            jest.advanceTimersByTime(500);
            await Promise.resolve();
        }
        
        agent['running'] = false;
        // Advance timers to exit the polling loop
        for (let i = 0; i < 20; i++) {
            now += 500;
            jest.advanceTimersByTime(500);
            await Promise.resolve();
        }
        
        await runPromise;
        
        expect(mockRedis.subscribe).toHaveBeenCalled();
        jest.useRealTimers();
    }, 20000);

    test('monitor positions in run loop', async () => {
        jest.useFakeTimers();
        let now = Date.now();
        jest.spyOn(Date, 'now').mockImplementation(() => now);
        
        agent['dbInitialized'] = true;
        agent['running'] = true;
        
        // Add a mock position
        const posId = 'p_mon_1';
        agent.positions.set(posId, {
            position_id: posId,
            mint: MINT_A,
            entry_price_sol: 0.001,
            tokens_received: 10000,
            state: 'OPEN',
            peak_price_sol: 0.001,
            price_buffer: []
        });
        
        // Mock polling interval to be short for test
        const fetchSpy = jest.spyOn(agent, 'fetchPrice').mockResolvedValue(0.0015);
        const updateSpy = jest.spyOn(agent, 'updatePositionState').mockResolvedValue(undefined);
        
        const runPromise = agent.run();
        
        // 1. Initial 3s wait
        now += 3500;
        jest.advanceTimersByTime(3500);
        await Promise.resolve();
        await Promise.resolve();
        
        // 2. Loop should have executed at least once
        expect(fetchSpy).toHaveBeenCalledWith(MINT_A);
        expect(updateSpy).toHaveBeenCalledWith(expect.anything(), 0.0015);
        
        agent['running'] = false;
        now += 10000;
        jest.advanceTimersByTime(10000);
        await Promise.resolve();
        await Promise.resolve();
        
        await runPromise;
        jest.useRealTimers();
    });
});
