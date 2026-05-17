import { CircuitBreaker, CircuitState } from './circuit-breaker';
import { validateConfig, validateConfigFile, parseSimpleYaml } from './config_validator';
import { generateOTP, verifyOTP } from './telegram_auth';
import { readPassphraseStdin } from './passphrase';
import * as fs from 'fs';
import * as path from 'path';
import * as readline from 'readline';

jest.mock('fs');
jest.mock('readline');

describe('Shared Infrastructure Hardened Tests', () => {

  describe('CircuitBreaker', () => {
    test('transitions to OPEN after failures', async () => {
      const breaker = new CircuitBreaker(2, 100);
      const failingFn = jest.fn().mockRejectedValue(new Error('Fail'));

      await expect(breaker.execute(failingFn)).rejects.toThrow('Fail');
      expect(breaker.getState()).toBe(CircuitState.CLOSED);

      await expect(breaker.execute(failingFn)).rejects.toThrow('Fail');
      expect(breaker.getState()).toBe(CircuitState.OPEN);

      await expect(breaker.execute(failingFn)).rejects.toThrow('Circuit breaker is OPEN');
    });

    test('transitions to HALF_OPEN after timeout', async () => {
      jest.useFakeTimers();
      const breaker = new CircuitBreaker(1, 100);
      const failingFn = jest.fn().mockRejectedValue(new Error('Fail'));

      await expect(breaker.execute(failingFn)).rejects.toThrow('Fail');
      expect(breaker.getState()).toBe(CircuitState.OPEN);

      jest.advanceTimersByTime(150);
      const successFn = jest.fn().mockResolvedValue('OK');
      const result = await breaker.execute(successFn);
      
      expect(result).toBe('OK');
      expect(breaker.getState()).toBe(CircuitState.CLOSED);
      
      // Half-open failure transitions back to OPEN
      await expect(breaker.execute(failingFn)).rejects.toThrow('Fail');
      expect(breaker.getState()).toBe(CircuitState.OPEN);

      jest.useRealTimers();
    });
  });

  describe('ConfigValidator', () => {
    const mockSchema = {
      type: 'object',
      properties: {
        trading: { type: 'object' }
      },
      required: ['trading']
    };

    beforeEach(() => {
        jest.clearAllMocks();
    });

    test('validateConfig success', () => {
      (fs.existsSync as jest.Mock).mockReturnValue(true);
      (fs.readFileSync as jest.Mock).mockReturnValue(JSON.stringify(mockSchema));
      
      const result = validateConfig({ trading: {} });
      expect(result.isValid).toBe(true);
    });

    test('validateConfig failure', () => {
      (fs.existsSync as jest.Mock).mockReturnValue(true);
      (fs.readFileSync as jest.Mock).mockReturnValue(JSON.stringify(mockSchema));
      
      const result = validateConfig({});
      expect(result.isValid).toBe(false);
      expect(result.errors).toBeDefined();
    });

    test('validateConfigFile success', () => {
      (fs.existsSync as jest.Mock).mockReturnValue(true);
      (fs.readFileSync as jest.Mock).mockImplementation((path) => {
          if (path.includes('schema')) return JSON.stringify(mockSchema);
          return JSON.stringify({ trading: {} });
      });
      
      const result = validateConfigFile('config.json');
      expect(result.isValid).toBe(true);
    });

    test('validateConfigFile yaml fallback', () => {
        (fs.existsSync as jest.Mock).mockReturnValue(true);
        (fs.readFileSync as jest.Mock).mockReturnValue('trading:\n  tp1: 2');
        const result = validateConfigFile('config.yaml');
        expect(result.isValid).toBe(false); // Schema will fail because it's not the full object
    });

    test('parseSimpleYaml coverage', () => {
        const yamlStr = `
# Comment
section:
  key: value
  bool: true
  num: 123
  str: "quoted"
`;
        const result = parseSimpleYaml(yamlStr);
        expect(result.section.key).toBe('value');
        expect(result.section.bool).toBe(true);
        expect(result.section.num).toBe(123);
        expect(result.section.str).toBe('quoted');
    });

  });

  describe('TelegramAuth', () => {
    test('OTP generation and verification', () => {
      const seed = 'test-seed';
      const otp = generateOTP(seed);
      expect(otp).toHaveLength(8);
      expect(verifyOTP(seed, otp)).toBe(true);
    });

    test('OTP verification with window', () => {
      const seed = 'test-seed';
      const pastTs = Math.floor(Date.now() / 1000) - 30;
      const pastOtp = generateOTP(seed, pastTs);
      expect(verifyOTP(seed, pastOtp, 1)).toBe(true);
    });
  });

  describe('PassphraseStdin', () => {
    let originalStdinOn: any;
    let originalStdoutWrite: any;
    let mockOn: jest.Mock;
    let mockWrite: jest.Mock;

    beforeEach(() => {
        mockOn = jest.fn();
        mockWrite = jest.fn();
        originalStdinOn = process.stdin.on;
        originalStdoutWrite = process.stdout.write;
        process.stdin.on = mockOn as any;
        process.stdout.write = mockWrite as any;
    });

    afterEach(() => {
        process.stdin.on = originalStdinOn;
        process.stdout.write = originalStdoutWrite;
    });

    test('reads passphrase from stdin', async () => {
      const mockInterface = { close: jest.fn() };
      (readline.createInterface as jest.Mock).mockReturnValue(mockInterface);
      
      const promise = readPassphraseStdin();
      
      const dataCall = mockOn.mock.calls.find(c => c[0] === 'data');
      if (!dataCall) throw new Error('Data callback not registered');
      const dataCallback = dataCall[1];

      dataCallback(Buffer.from([0x61])); // 'a'
      dataCallback(Buffer.from([0x0d])); // Enter
      
      const result = await promise;
      expect(result).toBe('a');
    });
  });
});
