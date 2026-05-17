import MockRedis, { MockRedisStore, resetMockRedis } from './mock_redis';

describe('MockRedisStore', () => {
  let store: MockRedisStore;

  beforeEach(() => {
    resetMockRedis();
    store = MockRedisStore.getInstance();
  });

  test('getInstance returns singleton', () => {
    const s1 = MockRedisStore.getInstance();
    const s2 = MockRedisStore.getInstance();
    expect(s1).toBe(s2);
  });

  test('get and set', () => {
    expect(store.get('key1')).toBeNull();
    store.set('key1', 'val1');
    expect(store.get('key1')).toBe('val1');
  });

  test('publish and subscribe with callbacks', () => {
    const cb = jest.fn();
    store.subscribe('ch1', cb);
    store.publish('ch1', 'hello');
    expect(cb).toHaveBeenCalledWith('hello');
  });

  test('unsubscribe removes callback', () => {
    const cb = jest.fn();
    store.subscribe('ch1', cb);
    store.unsubscribe('ch1', cb);
    store.publish('ch1', 'hello');
    expect(cb).not.toHaveBeenCalled();
  });

  test('publish notifies multiple subscribers', () => {
    const cb1 = jest.fn();
    const cb2 = jest.fn();
    store.subscribe('ch1', cb1);
    store.subscribe('ch1', cb2);
    store.publish('ch1', 'msg');
    expect(cb1).toHaveBeenCalledWith('msg');
    expect(cb2).toHaveBeenCalledWith('msg');
  });

  test('publish on different channel does not notify', () => {
    const cb = jest.fn();
    store.subscribe('ch1', cb);
    store.publish('ch2', 'msg');
    expect(cb).not.toHaveBeenCalled();
  });

  test('callback error is caught', () => {
    const cb = jest.fn().mockImplementation(() => { throw new Error('cb err'); });
    store.subscribe('ch1', cb);
    expect(() => store.publish('ch1', 'msg')).not.toThrow();
    expect(cb).toHaveBeenCalled();
  });

  test('onMessage and offMessage', () => {
    const cb = jest.fn();
    store.onMessage(cb);
    store.publish('ch', 'msg');
    expect(cb).toHaveBeenCalledWith('ch', 'msg');
    store.offMessage(cb);
    store.publish('ch2', 'msg2');
    expect(cb).toHaveBeenCalledTimes(1);
  });

  test('reset clears all data and subscriptions', () => {
    store.set('k', 'v');
    const cb = jest.fn();
    store.subscribe('ch', cb);
    store.onMessage(cb);
    store.reset();
    expect(store.get('k')).toBeNull();
    store.publish('ch', 'msg');
    expect(cb).not.toHaveBeenCalled();
  });

  test('emitter is notified on publish', () => {
    const cb = jest.fn();
    store.onMessage(cb);
    store.publish('ch', 'msg');
    expect(cb).toHaveBeenCalledWith('ch', 'msg');
  });
});

describe('MockRedis', () => {
  let mock: MockRedis;

  beforeEach(() => {
    resetMockRedis();
    mock = new MockRedis();
  });

  test('connect and ping', async () => {
    await mock.connect();
    const result = await mock.ping();
    expect(result).toBe('PONG');
  });

  test('get returns null for missing key', async () => {
    const val = await mock.get('nonexistent');
    expect(val).toBeNull();
  });

  test('set and get', async () => {
    await mock.set('key', 'value');
    const val = await mock.get('key');
    expect(val).toBe('value');
  });

  test('duplicate creates copy with same subscriptions', async () => {
    const cb = jest.fn();
    await mock.subscribe('ch', cb);
    const dup = mock.duplicate();
    expect(dup).toBeInstanceOf(MockRedis);
    await dup.publish('ch', 'msg');
    expect(cb).toHaveBeenCalledWith('msg');
  });

  test('duplicate independent from original', async () => {
    const cb1 = jest.fn();
    const cb2 = jest.fn();
    await mock.subscribe('ch', cb1);
    const dup = mock.duplicate();
    await dup.subscribe('ch', cb2);
    await mock.publish('ch', 'msg');
    expect(cb1).toHaveBeenCalled();
    expect(cb2).toHaveBeenCalled();
  });

  test('quit clears subscriptions', async () => {
    const cb = jest.fn();
    await mock.subscribe('ch', cb);
    await mock.quit();
    await mock.publish('ch', 'msg');
    expect(cb).not.toHaveBeenCalled();
  });

  test('publish delivers message to subscribers', async () => {
    const cb = jest.fn();
    await mock.subscribe('ch', cb);
    await mock.publish('ch', 'test message');
    expect(cb).toHaveBeenCalledWith('test message');
  });

  test('subscribe stores callback', async () => {
    const cb = jest.fn();
    await mock.subscribe('ch1', cb);
    const cb2 = jest.fn();
    await mock.subscribe('ch2', cb2);
    await mock.publish('ch1', 'for ch1');
    expect(cb).toHaveBeenCalledWith('for ch1');
    expect(cb2).not.toHaveBeenCalled();
  });

  test('resetMockRedis clears cross-instance state', async () => {
    const mock2 = new MockRedis();
    await mock.set('shared', 'data');
    resetMockRedis();
    const val = await mock2.get('shared');
    expect(val).toBeNull();
  });
});
