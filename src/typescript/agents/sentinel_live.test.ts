import * as fs from 'fs';
import axios from 'axios';
import { Connection, Keypair, Transaction, PublicKey, SystemProgram } from '@solana/web3.js';

// Constants
const SHARED_KEYPAIR = Keypair.generate();
const MINT_A = 'EPjFW36vXT3Z3pJvAbYTNp3Xbw7B637vH8G2fEU3XgA';

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

describe('SentinelAgent Live Coverage', () => {
    let SentinelAgent: any;
    let agent: any;
    let mockRedis: any;

    beforeAll(() => {
        process.env.MTUS_ENVIRONMENT = 'production';
        (fs.readFileSync as jest.Mock).mockReturnValue('trading:\n  tp1_multiplier: 2.0');
        SentinelAgent = require('./sentinel').SentinelAgent;
    });

    beforeEach(() => {
        jest.clearAllMocks();
        const Redis = require('ioredis');
        mockRedis = new Redis();
        agent = new SentinelAgent({}, mockRedis);
        agent.config = { trading: { tp1_multiplier: 2.0 } };
        agent['keypair'] = SHARED_KEYPAIR;
        
        mockAres.rateLimitedRequest.mockImplementation(async (fn: any) => ({
            outAmount: '1000000', swapTransaction: getDummyTxBase64(SHARED_KEYPAIR.publicKey)
        }));
        (axios.get as jest.Mock).mockImplementation((url: string) => {
            if (url.includes('pump.fun/coins/')) return Promise.resolve({ data: { virtual_sol_reserves: 40_000_000_000, virtual_token_reserves: 1_000_000_000, complete: false } });
            return Promise.resolve({ data: {} });
        });
    });

    test('Live mode production sell (Jupiter)', async () => {
        const pos: any = { position_id: 'p_live', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001, state: 'OPEN', entry_timestamp_utc: new Date().toISOString() };
        await agent.sellPortion(pos, 1.0, 'tp2_hit');
        expect(mockConn.sendRawTransaction).toHaveBeenCalled();
    });

    test('Live mode production sell (Pump.fun)', async () => {
        const pos: any = { position_id: 'p_pump', mint: MINT_A, tokens_received: 10000, entry_price_sol: 0.001, peak_price_sol: 0.001, state: 'OPEN', entry_timestamp_utc: new Date().toISOString() };
        // Trigger isPump = true via axios mock in beforeEach
        await agent.sellPortion(pos, 1.0, 'tp2_hit');
        expect(mockConn.sendRawTransaction).toHaveBeenCalled();
    });
});
