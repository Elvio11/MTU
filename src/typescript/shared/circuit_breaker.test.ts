import { CircuitBreaker, CircuitState } from './circuit-breaker';

describe('CircuitBreaker', () => {
  test('executes successfully', async () => {
    const cb = new CircuitBreaker(3, 1000);
    expect(await cb.execute(async () => 'ok')).toBe('ok');
    expect(cb.getState()).toBe(CircuitState.CLOSED);
  });

  test('opens after threshold failures', async () => {
    const cb = new CircuitBreaker(2, 1000);
    const fn = jest.fn().mockRejectedValue(new Error('fail'));
    await expect(cb.execute(fn)).rejects.toThrow('fail');
    await expect(cb.execute(fn)).rejects.toThrow('fail');
    expect(cb.getState()).toBe(CircuitState.OPEN);
    await expect(cb.execute(fn)).rejects.toThrow('Circuit breaker is OPEN');
  });

  test('half-open transitions to closed on success', async () => {
    jest.useFakeTimers();
    const cb = new CircuitBreaker(1, 100);
    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow('fail');
    expect(cb.getState()).toBe(CircuitState.OPEN);
    jest.advanceTimersByTime(150);
    expect(await cb.execute(() => Promise.resolve('ok'))).toBe('ok');
    expect(cb.getState()).toBe(CircuitState.CLOSED);
    jest.useRealTimers();
  });

  test('uses default values', async () => {
    const cb = new CircuitBreaker();
    const fn = jest.fn().mockRejectedValue(new Error('fail'));
    await expect(cb.execute(fn)).rejects.toThrow('fail');
    await expect(cb.execute(fn)).rejects.toThrow('fail');
    await expect(cb.execute(fn)).rejects.toThrow('fail');
    expect(cb.getState()).toBe(CircuitState.OPEN);
  });
});
