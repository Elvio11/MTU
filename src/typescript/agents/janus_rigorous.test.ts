import { Keypair, LAMPORTS_PER_SOL } from '@solana/web3.js';
import * as channels from '../shared/channels';

// These variables will be assigned in beforeEach
let mockGetBalance: any;
let mockSendAndConfirmTransaction: any;
let mockLoadKeypair: any;

// Mock shared modules
jest.mock('../shared/keystore', () => ({
  loadKeypairFromKeystore: (path: string, pass: string) => mockLoadKeypair(path, pass),
}));

// Mock Redis with spied methods
jest.mock('ioredis', () => {
  const MockRedis = require('../shared/mock_redis').default;
  const originalDuplicate = MockRedis.prototype.duplicate;
  MockRedis.prototype.duplicate = jest.fn().mockImplementation(function(this: any) {
    const d = originalDuplicate.call(this);
    d.publish = jest.fn().mockImplementation(d.publish.bind(d));
    d.subscribe = jest.fn().mockImplementation(d.subscribe.bind(d));
    return d;
  });
  // Make publish and quit jest mocks while keeping original behavior
  MockRedis.prototype.publish = jest.fn().mockImplementation(MockRedis.prototype.publish);
  MockRedis.prototype.quit = jest.fn().mockImplementation(MockRedis.prototype.quit);
  return MockRedis;
});

// Mock Web3
jest.mock('@solana/web3.js', () => {
    const actual = jest.requireActual('@solana/web3.js');
    return {
        ...actual,
        Connection: jest.fn().mockImplementation(() => ({
            getBalance: (p: any) => mockGetBalance(p),
        })),
        sendAndConfirmTransaction: (c: any, t: any, s: any) => mockSendAndConfirmTransaction(c, t, s),
    };
});

describe('JanusAgent Rigorous Tests', () => {
  let mockRedis: any;

  beforeAll(() => {
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterAll(() => {
    if ((console.log as any).mockRestore) (console.log as any).mockRestore();
    if ((console.error as any).mockRestore) (console.error as any).mockRestore();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    const { resetMockRedis } = require('../shared/mock_redis');
    resetMockRedis();
    
    // Initialize mocks for each test
    mockGetBalance = jest.fn().mockResolvedValue(1 * LAMPORTS_PER_SOL);
    mockSendAndConfirmTransaction = jest.fn().mockResolvedValue('test_sig');
    mockLoadKeypair = jest.fn();

    const Redis = require('ioredis');
    mockRedis = new Redis();
  });

  test('loadWallets successfully loads both keypairs', async () => {
    const { JanusAgent } = require('./janus');
    const sniperKp = Keypair.generate();
    const mainKp = Keypair.generate();
    mockLoadKeypair.mockResolvedValueOnce(sniperKp).mockResolvedValueOnce(mainKp);

    const agent = new JanusAgent({}, mockRedis);
    await agent.loadWallets('p1', 'p2');

    expect(agent['sniperKeypair']).toBe(sniperKp);
    expect(agent['mainKeypair']).toBe(mainKp);
  });

  test('sweepProfits executes when balance is above threshold', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    const sniperKp = Keypair.generate();
    const mainKp = Keypair.generate();
    agent['sniperKeypair'] = sniperKp;
    agent['mainKeypair'] = mainKp;

    mockGetBalance.mockResolvedValue(2.5 * LAMPORTS_PER_SOL);
    mockSendAndConfirmTransaction.mockResolvedValue('test_sig');

    await agent['sweepProfits'](2.5);

    expect(mockSendAndConfirmTransaction).toHaveBeenCalled();
    expect(mockRedis.publish).toHaveBeenCalledWith(
      channels.CHANNEL_SWEEP_COMPLETED,
      expect.stringContaining('sweep_completed')
    );
  });

  test('sweepProfits skips when balance is below threshold', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    const sniperKp = Keypair.generate();
    const mainKp = Keypair.generate();
    agent['sniperKeypair'] = sniperKp;
    agent['mainKeypair'] = mainKp;

    await agent['sweepProfits'](0.4);

    expect(mockSendAndConfirmTransaction).not.toHaveBeenCalled();
  });

  test('sweepProfits handles transaction failure', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    const sniperKp = Keypair.generate();
    const mainKp = Keypair.generate();
    agent['sniperKeypair'] = sniperKp;
    agent['mainKeypair'] = mainKp;

    mockSendAndConfirmTransaction.mockRejectedValue(new Error('Network error'));

    await agent['sweepProfits'](3.0);

    expect(mockRedis.publish).toHaveBeenCalledWith(
      channels.CHANNEL_TRADE_FAILED,
      expect.stringContaining('Sweep failed')
    );
  });

  test('stop sets running to false and quits redis', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    agent['running'] = true;

    await agent.stop();

    expect(agent['running']).toBe(false);
    expect(mockRedis.quit).toHaveBeenCalled();
  });

  test('getInstance returns a singleton instance and handles existing instance', () => {
    const { JanusAgent } = require('./janus');
    JanusAgent['instance'] = null; // Reset singleton
    const instance1 = JanusAgent.getInstance({ a: 1 }, mockRedis);
    const instance2 = JanusAgent.getInstance({ b: 2 }, mockRedis);
    expect(instance1).toBe(instance2);
    expect(instance1['config']).toEqual({ a: 1 });
  });

  test('constructor and loadWallets handle missing env vars', async () => {
    const { JanusAgent } = require('./janus');
    const oldRpc = process.env.HELIUS_RPC_URL;
    const oldSniper = process.env.SNIPER_KEYSTORE_PATH;
    const oldMain = process.env.MAIN_KEYSTORE_PATH;
    
    delete process.env.HELIUS_RPC_URL;
    delete process.env.SNIPER_KEYSTORE_PATH;
    delete process.env.MAIN_KEYSTORE_PATH;

    const agent = new JanusAgent(); // Hit constructor default config
    expect(agent['config']).toEqual({});
    
    mockLoadKeypair.mockResolvedValue(Keypair.generate());
    await agent.loadWallets('p1', 'p2');
    
    expect(mockLoadKeypair).toHaveBeenCalledWith('keystore/sniper.json', 'p1');
    expect(mockLoadKeypair).toHaveBeenCalledWith('keystore/main.json', 'p2');

    process.env.HELIUS_RPC_URL = oldRpc;
    process.env.SNIPER_KEYSTORE_PATH = oldSniper;
    process.env.MAIN_KEYSTORE_PATH = oldMain;
  });

  test('getInstance handles default config parameter', () => {
    const { JanusAgent } = require('./janus');
    JanusAgent['instance'] = null;
    const agent = JanusAgent.getInstance(); // Hit default config={}
    expect(agent['config']).toEqual({});
  });

  test('run loop handles missing keypairs', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    await expect(agent.run()).rejects.toThrow('Wallets not loaded');
  });

  test('loadWallets throws error on keystore failure', async () => {
    const { JanusAgent } = require('./janus');
    mockLoadKeypair.mockRejectedValue(new Error('File not found'));

    const agent = new JanusAgent({}, mockRedis);
    await expect(agent.loadWallets('p1', 'p2')).rejects.toThrow('Failed to load wallets: File not found');
  });

  test('run loop executes sweep and waits', async () => {
    jest.useFakeTimers();
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    const sniperKp = Keypair.generate();
    const mainKp = Keypair.generate();
    agent['sniperKeypair'] = sniperKp;
    agent['mainKeypair'] = mainKp;

    mockGetBalance.mockResolvedValue(2.5 * LAMPORTS_PER_SOL);
    mockSendAndConfirmTransaction.mockResolvedValue('sig');

    // Start the loop in background
    const runPromise = agent.run();

    // Fast-forward past the first iteration
    // The loop body runs once immediately, then hits the timeout
    // We need to give it a tick to run the async work
    await Promise.resolve(); // allow initial getBalance/sweepProfits to run
    
    expect(mockGetBalance).toHaveBeenCalled();
    expect(mockSendAndConfirmTransaction).toHaveBeenCalled();

    // Stop the loop
    agent.stop();
    
    // Fast-forward timers to clear any remaining setTimeout
    jest.runAllTimers();
    await runPromise;
    
    jest.useRealTimers();
  });

  test('run loop handles error inside the loop', async () => {
    jest.useFakeTimers();
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    agent['sniperKeypair'] = Keypair.generate();
    agent['mainKeypair'] = Keypair.generate();

    mockGetBalance.mockRejectedValue(new Error('RPC Down'));

    const runPromise = agent.run();
    await Promise.resolve();

    expect(mockGetBalance).toHaveBeenCalled();
    
    agent.stop();
    jest.runAllTimers();
    await runPromise;
    jest.useRealTimers();
  });

  test('sweepProfits skips tiny amounts', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    agent['sniperKeypair'] = Keypair.generate();
    agent['mainKeypair'] = Keypair.generate();

    // 0.5 RESERVE + 0.04 = 0.54
    await agent['sweepProfits'](0.54);

    expect(mockSendAndConfirmTransaction).not.toHaveBeenCalled();
  });

  test('sweepProfits handles missing keypairs early return', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    // sniperKeypair is null by default
    await agent['sweepProfits'](3.0);

    expect(mockSendAndConfirmTransaction).not.toHaveBeenCalled();
  });

  test('checkSniperBalance returns 0 if keypair missing', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    
    const bal = await agent.checkSniperBalance();
    expect(bal).toBe(0);
  });

  test('checkSniperBalance returns balance in SOL', async () => {
    const { JanusAgent } = require('./janus');
    const agent = new JanusAgent({}, mockRedis);
    agent['sniperKeypair'] = Keypair.generate();
    mockGetBalance.mockResolvedValue(1.5 * LAMPORTS_PER_SOL);

    const bal = await agent.checkSniperBalance();
    expect(bal).toBe(1.5);
  });
});
