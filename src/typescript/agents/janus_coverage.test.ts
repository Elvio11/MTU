import * as db from '../shared/db';
import Redis from 'ioredis';
import { JanusAgent } from './janus';
import { Keypair, Connection } from '@solana/web3.js';
import * as keystore from '../shared/keystore';

jest.mock('../shared/db', () => ({
  insertAuditLog: { run: jest.fn() },
  shutdownDB: jest.fn(),
}));

jest.mock('ioredis', () => require('../shared/mock_redis').default);
jest.mock('../shared/keystore');
jest.mock('@solana/web3.js', () => {
    const actual = jest.requireActual('@solana/web3.js');
    return {
        ...actual,
        Connection: jest.fn().mockImplementation(() => ({
            getBalance: jest.fn().mockResolvedValue(3 * 1e9), // 3 SOL
        })),
        sendAndConfirmTransaction: jest.fn().mockResolvedValue('sweep_sig'),
    };
});

describe('JanusAgent Coverage Tests', () => {
  let mockRedis: any;

  beforeEach(() => {
    jest.clearAllMocks();
    const { resetMockRedis } = require('../shared/mock_redis');
    resetMockRedis();
    const Redis = require('ioredis');
    mockRedis = new Redis();
    
    mockRedis.publish = jest.fn();
    mockRedis.quit = jest.fn();
    
    jest.useFakeTimers();
  });

  afterEach(() => {
      jest.useRealTimers();
  });

  test('init and loadWallets', async () => {
    (keystore.loadKeypairFromKeystore as jest.Mock).mockResolvedValue(Keypair.generate());
    const agent = new JanusAgent({}, mockRedis);
    await agent.loadWallets('pass1', 'pass2');
    expect(agent).toBeDefined();
    expect(keystore.loadKeypairFromKeystore).toHaveBeenCalledTimes(2);
  });

  test('sweepProfits logic', async () => {
    (keystore.loadKeypairFromKeystore as jest.Mock).mockResolvedValue(Keypair.generate());
    const agent = new JanusAgent({}, mockRedis);
    await agent.loadWallets('pass1', 'pass2');
    
    await (agent as any).sweepProfits(3.0);
    
    expect(mockRedis.publish).toHaveBeenCalledWith(
        expect.stringContaining('sweep_completed'),
        expect.stringContaining('sweep_sig')
    );
  });

  test('checkSniperBalance utility', async () => {
    (keystore.loadKeypairFromKeystore as jest.Mock).mockResolvedValue(Keypair.generate());
    const agent = new JanusAgent({}, mockRedis);
    await agent.loadWallets('pass1', 'pass2');
    
    const balance = await agent.checkSniperBalance();
    expect(balance).toBe(3);
  });

  test('getInstance singleton', () => {
    const instance1 = JanusAgent.getInstance({}, mockRedis);
    const instance2 = JanusAgent.getInstance({}, mockRedis);
    expect(instance1).toBe(instance2);
  });

  test('loadWallets error path', async () => {
    (keystore.loadKeypairFromKeystore as jest.Mock).mockRejectedValue(new Error('Keystore error'));
    const agent = new JanusAgent({}, mockRedis);
    await expect(agent.loadWallets('pass1', 'pass2')).rejects.toThrow('Failed to load wallets: Keystore error');
  });

  test('run loop handles getBalance error', async () => {
    (keystore.loadKeypairFromKeystore as jest.Mock).mockResolvedValue(Keypair.generate());
    const agent = new JanusAgent({}, mockRedis);
    await agent.loadWallets('pass1', 'pass2');
    
    const mockConn = (agent as any).connection;
    mockConn.getBalance.mockRejectedValueOnce(new Error('RPC Down'));
    
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
    
    const runPromise = agent.run();
    jest.advanceTimersByTime(100);
    await agent.stop();
    jest.runOnlyPendingTimers();
    await runPromise;
    
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Janus: RPC Down'));
    consoleSpy.mockRestore();
  });

  test('sweepProfits error path', async () => {
    (keystore.loadKeypairFromKeystore as jest.Mock).mockResolvedValue(Keypair.generate());
    const agent = new JanusAgent({}, mockRedis);
    await agent.loadWallets('pass1', 'pass2');
    
    const { sendAndConfirmTransaction } = require('@solana/web3.js');
    sendAndConfirmTransaction.mockRejectedValueOnce(new Error('Sweep Fail'));
    
    await (agent as any).sweepProfits(3.0);
    
    expect(mockRedis.publish).toHaveBeenCalledWith(
        expect.stringContaining('trade_failed'),
        expect.stringContaining('Sweep failed: Sweep Fail')
    );
  });

  test('run error before wallets loaded', async () => {
    const agent = new JanusAgent({}, mockRedis);
    await expect(agent.run()).rejects.toThrow('Wallets not loaded');
  });

  test('run loop successful iteration', async () => {
    (keystore.loadKeypairFromKeystore as jest.Mock).mockResolvedValue(Keypair.generate());
    const agent = new JanusAgent({}, mockRedis);
    await agent.loadWallets('pass1', 'pass2');
    
    const mockConn = (agent as any).connection;
    mockConn.getBalance.mockResolvedValue(3 * 1e9);
    
    const sweepSpy = jest.spyOn(agent as any, 'sweepProfits').mockResolvedValue(undefined);
    
    const runPromise = agent.run();
    
    // Advance timers to allow first loop iteration to complete
    await jest.advanceTimersByTimeAsync(100);
    agent['running'] = false;
    await jest.advanceTimersByTimeAsync(61000);
    
    await runPromise;
    
    expect(sweepSpy).toHaveBeenCalled();
    sweepSpy.mockRestore();
  });
});
