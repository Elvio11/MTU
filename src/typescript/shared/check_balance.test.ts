import { Connection, PublicKey } from '@solana/web3.js';

jest.mock('@solana/web3.js', () => {
  const mockConnection = { getBalance: jest.fn() };
  return {
    Connection: jest.fn().mockImplementation(() => mockConnection),
    PublicKey: jest.fn().mockImplementation((key: string) => ({
      toBase58: () => key,
    })),
  };
});

jest.mock('dotenv', () => ({ config: jest.fn() }));

describe('check_balance', () => {
  const originalLog = console.log;
  const originalWarn = console.warn;
  const originalError = console.error;

  afterEach(() => {
    console.log = originalLog;
    console.warn = originalWarn;
    console.error = originalError;
  });

  test('runs top-level checkBalances successfully', async () => {
    const mockConn = new Connection('');
    (mockConn.getBalance as jest.Mock).mockResolvedValue(1_000_000_000);

    const msgs: string[] = [];
    console.log = (...args: any[]) => { msgs.push(args.join(' ')); };
    console.warn = (...args: any[]) => { msgs.push(args.join(' ')); };
    console.error = (...args: any[]) => { msgs.push(args.join(' ')); };

    jest.isolateModules(() => {
      require('./check_balance');
    });

    await new Promise(r => setTimeout(r, 50));
    expect(msgs.some(m => m.includes('Sniper Wallet'))).toBe(true);
  });

  test('handles RPC error gracefully', async () => {
    const mockConn = new Connection('');
    (mockConn.getBalance as jest.Mock).mockRejectedValue(new Error('RPC error'));

    const msgs: string[] = [];
    console.log = (...args: any[]) => { msgs.push(args.join(' ')); };
    console.warn = (...args: any[]) => { msgs.push(args.join(' ')); };
    console.error = (...args: any[]) => { msgs.push(args.join(' ')); };

    jest.isolateModules(() => {
      require('./check_balance');
    });

    await new Promise(r => setTimeout(r, 50));
    expect(msgs.some(m => m.includes('Failed to fetch'))).toBe(true);
  });

  test('warns when sniper balance is low', async () => {
    const mockConn = new Connection('');
    (mockConn.getBalance as jest.Mock).mockResolvedValue(10_000_000);

    const msgs: string[] = [];
    console.log = (...args: any[]) => { msgs.push(args.join(' ')); };
    console.warn = (...args: any[]) => { msgs.push(args.join(' ')); };
    console.error = (...args: any[]) => { msgs.push(args.join(' ')); };

    jest.isolateModules(() => {
      require('./check_balance');
    });

    await new Promise(r => setTimeout(r, 50));
    expect(msgs.some(m => m.includes('low'))).toBe(true);
  });
});
