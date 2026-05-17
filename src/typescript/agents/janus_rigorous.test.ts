import { JanusAgent } from './janus';
import { Connection, Keypair, LAMPORTS_PER_SOL, Transaction, sendAndConfirmTransaction } from '@solana/web3.js';
import { createEnvelope } from '../shared/envelope';
import { CHANNEL_SWEEP_COMPLETED, CHANNEL_TRADE_FAILED } from '../shared/channels';

jest.mock('@solana/web3.js', () => {
    const original = jest.requireActual('@solana/web3.js');
    return {
        ...original,
        Connection: jest.fn().mockImplementation(() => ({
            getBalance: jest.fn().mockResolvedValue(3 * LAMPORTS_PER_SOL), // 3 SOL
        })),
        sendAndConfirmTransaction: jest.fn().mockResolvedValue('test_sweep_sig'),
    };
});

jest.mock('../shared/keystore', () => ({
    loadKeypairFromKeystore: jest.fn().mockResolvedValue(jest.requireActual('@solana/web3.js').Keypair.generate()),
}));

describe('JanusAgent Rigorous Tests', () => {
    let mockRedis: any;

    beforeEach(() => {
        jest.clearAllMocks();
        mockRedis = {
            publish: jest.fn().mockResolvedValue(1),
            quit: jest.fn().mockResolvedValue('OK'),
        };
        process.env.MTUS_ENVIRONMENT = 'paper';
    });

    test('init and isPaperMode', async () => {
        delete process.env.MTUS_ENVIRONMENT;
        const agent = new JanusAgent({ system: { environment: 'production' } }, mockRedis);
        await agent.init(mockRedis);
        expect(agent.isPaperMode()).toBe(false);
        
        process.env.MTUS_ENVIRONMENT = 'paper';
        expect(agent.isPaperMode()).toBe(true);
    });

    test('getInstance singleton', () => {
        const instance1 = JanusAgent.getInstance({ a: 1 });
        const instance2 = JanusAgent.getInstance({ a: 2 });
        expect(instance1).toBe(instance2);
    });

    test('loadWallets and checkSniperBalance', async () => {
        const agent = new JanusAgent({}, mockRedis);
        await agent.loadWallets('p1', 'p2');
        const balance = await agent.checkSniperBalance();
        expect(balance).toBe(3);
    });

    test('sweepProfits success', async () => {
        const agent = new JanusAgent({}, mockRedis);
        await agent.loadWallets('p1', 'p2');
        
        // @ts-ignore
        await agent.sweepProfits(3.0);
        
        expect(sendAndConfirmTransaction).toHaveBeenCalled();
        expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_SWEEP_COMPLETED, expect.stringContaining('sweep_completed'));
    });

    test('sweepProfits skip if tiny', async () => {
        const agent = new JanusAgent({}, mockRedis);
        await agent.loadWallets('p1', 'p2');
        
        // RESERVE is 0.5, current is 0.52 -> amountToSweep is 0.02 (<= 0.05)
        // @ts-ignore
        await agent.sweepProfits(0.52);
        
        expect(sendAndConfirmTransaction).not.toHaveBeenCalled();
    });

    test('sweepProfits error handling', async () => {
        const agent = new JanusAgent({}, mockRedis);
        await agent.loadWallets('p1', 'p2');
        (sendAndConfirmTransaction as jest.Mock).mockRejectedValueOnce(new Error('RPC Error'));
        
        // @ts-ignore
        await agent.sweepProfits(3.0);
        
        expect(mockRedis.publish).toHaveBeenCalledWith(CHANNEL_TRADE_FAILED, expect.stringContaining('Sweep failed'));
    });

    test('run loop and stop', async () => {
        jest.useFakeTimers();
        const agent = new JanusAgent({}, mockRedis);
        await agent.loadWallets('p1', 'p2');
        
        const mockConn = (agent as any).connection;
        mockConn.getBalance.mockResolvedValueOnce(3 * LAMPORTS_PER_SOL);
        
        const runPromise = agent.run();
        
        // Advance past first iteration
        await jest.advanceTimersByTimeAsync(100);
        await agent.stop();
        // Advance to unblock polling timeout
        await jest.advanceTimersByTimeAsync(61000);
        await runPromise;
        
        expect(mockConn.getBalance).toHaveBeenCalled();
        jest.useRealTimers();
    }, 10000);

    test('run loop error handling', async () => {
        jest.useFakeTimers();
        const agent = new JanusAgent({}, mockRedis);
        await agent.loadWallets('p1', 'p2');
        
        const mockConn = (agent as any).connection;
        mockConn.getBalance.mockRejectedValueOnce(new Error('Network down'));
        
        const runPromise = agent.run();
        
        await jest.advanceTimersByTimeAsync(100);
        await agent.stop();
        await jest.advanceTimersByTimeAsync(61000);
        await runPromise;
        jest.useRealTimers();
    }, 10000);
});
