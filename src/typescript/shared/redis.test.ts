import { createRedisClient } from './redis';

jest.mock('ioredis', () => {
  const mockRedis = jest.fn();
  return mockRedis;
});

describe('createRedisClient', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    delete process.env.REDIS_URL;
  });

  test('falls back to mock redis when connection fails', async () => {
    const Redis = require('ioredis');
    Redis.mockImplementation(() => {
      return { on: jest.fn(), once: jest.fn() };
    });
    const client = await createRedisClient();
    expect(client).toBeDefined();
  }, 10000);

  test('falls back to mock on redis error', async () => {
    const Redis = require('ioredis');
    Redis.mockImplementation(() => ({
      on: jest.fn(),
      once: jest.fn((event: string, cb: Function) => {
        if (event === 'error') cb(new Error('Connection refused'));
      }),
    }));
    const client = await createRedisClient();
    expect(client).toBeDefined();
  });

  test('creates ioredis client on successful connection', async () => {
    const Redis = require('ioredis');
    const mockClient = {
      on: jest.fn(),
      once: jest.fn((event: string, cb: Function) => {
        if (event === 'ready') cb();
      }),
      quit: jest.fn(),
    };
    Redis.mockImplementation(() => mockClient);
    const client = await createRedisClient();
    expect(client).toBe(mockClient);
  });

  test('retryStrategy returns null when times > 3', () => {
    const Redis = require('ioredis');
    let capturedRetryStrategy: Function | null = null;
    Redis.mockImplementation((url: string, opts: any) => {
      capturedRetryStrategy = opts.retryStrategy;
      return { on: jest.fn(), once: jest.fn() };
    });
    createRedisClient();
    expect(capturedRetryStrategy).toBeDefined();
    if (capturedRetryStrategy) {
      expect(capturedRetryStrategy(4)).toBeNull();
    }
  });

  test('retryStrategy returns delay when times <= 3', () => {
    const Redis = require('ioredis');
    let capturedRetryStrategy: Function | null = null;
    Redis.mockImplementation((url: string, opts: any) => {
      capturedRetryStrategy = opts.retryStrategy;
      return { on: jest.fn(), once: jest.fn() };
    });
    createRedisClient();
    expect(capturedRetryStrategy).toBeDefined();
    if (capturedRetryStrategy) {
      const delay = capturedRetryStrategy(2);
      expect(delay).toBeLessThanOrEqual(3000);
    }
  });

  test('falls back to minimal mock when MockRedis require fails', async () => {
    jest.resetModules();
    jest.doMock('ioredis', () => jest.fn().mockImplementation(() => ({ on: jest.fn(), once: jest.fn() })));
    jest.doMock('./mock_redis', () => ({}));
    const { createRedisClient: crc } = await import('./redis');
    const client = await crc();
    expect(client).toBeDefined();
    expect(typeof (client as any).publish).toBe('function');
    expect(typeof (client as any).subscribe).toBe('function');
    expect(typeof (client as any).get).toBe('function');
    expect(typeof (client as any).set).toBe('function');
    expect(typeof (client as any).duplicate).toBe('function');
    expect(typeof (client as any).quit).toBe('function');
    await (client as any).publish('ch', 'msg');
    await (client as any).subscribe('ch');
    await (client as any).get('key');
    await (client as any).set('key', 'val');
    (client as any).on('event', () => {});
    const sub = (client as any).duplicate();
    expect(typeof sub.subscribe).toBe('function');
    await (client as any).quit();
  });
});
