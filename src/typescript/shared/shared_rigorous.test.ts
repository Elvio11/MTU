import { isOperationalWindowActive } from './operational-window';
import { CircuitBreaker, CircuitState } from './circuit-breaker';
import { readPassphraseStdin } from './passphrase';
import { generateOTP, verifyOTP } from './telegram_auth';
import { createKeystore, loadKeypairFromKeystore } from './keystore';
import { validateConfig, validateConfigFile, validateConfigAtStartup } from './config_validator';
import * as fs from 'fs';
import * as readline from 'readline';
import { DateTime } from 'luxon';
import { Keypair } from '@solana/web3.js';
import * as yaml from 'js-yaml';

jest.mock('fs');
jest.mock('readline');
jest.mock('argon2', () => ({
    hash: jest.fn().mockImplementation((pass) => {
        // Return 32 bytes derived from passphrase
        const buf = Buffer.alloc(32);
        buf.write(pass);
        return Promise.resolve(buf);
    }),
    argon2id: 2
}));

describe('Shared Modules Rigorous Tests', () => {

    describe('operational-window.ts', () => {
        const mockConfig = {
            system: {
                operational_window: {
                    start_hour_ist: 9,
                    end_hour_ist: 17
                }
            }
        };

        beforeEach(() => {
            jest.clearAllMocks();
        });

        test('isOperationalWindowActive returns true when within standard window', () => {
            (fs.readFileSync as jest.Mock).mockReturnValue(yaml.dump(mockConfig));
            // Mock current time to 10:00 IST
            const mockNow = DateTime.fromObject({ hour: 10 }, { zone: 'Asia/Kolkata' }).toUTC();
            jest.spyOn(DateTime, 'utc').mockReturnValue(mockNow);

            expect(isOperationalWindowActive()).toBe(true);
        });

        test('isOperationalWindowActive returns false when outside standard window', () => {
            (fs.readFileSync as jest.Mock).mockReturnValue(yaml.dump(mockConfig));
            // Mock current time to 18:00 IST
            const mockNow = DateTime.fromObject({ hour: 18 }, { zone: 'Asia/Kolkata' }).toUTC();
            jest.spyOn(DateTime, 'utc').mockReturnValue(mockNow);

            expect(isOperationalWindowActive()).toBe(false);
        });

        test('isOperationalWindowActive handles over-midnight window', () => {
            const midnightConfig = {
                system: {
                    operational_window: {
                        start_hour_ist: 22,
                        end_hour_ist: 6
                    }
                }
            };
            (fs.readFileSync as jest.Mock).mockReturnValue(yaml.dump(midnightConfig));

            // 23:00 IST
            jest.spyOn(DateTime, 'utc').mockReturnValue(DateTime.fromObject({ hour: 23 }, { zone: 'Asia/Kolkata' }).toUTC());
            expect(isOperationalWindowActive()).toBe(true);

            // 03:00 IST
            jest.spyOn(DateTime, 'utc').mockReturnValue(DateTime.fromObject({ hour: 3 }, { zone: 'Asia/Kolkata' }).toUTC());
            expect(isOperationalWindowActive()).toBe(true);

            // 12:00 IST
            jest.spyOn(DateTime, 'utc').mockReturnValue(DateTime.fromObject({ hour: 12 }, { zone: 'Asia/Kolkata' }).toUTC());
            expect(isOperationalWindowActive()).toBe(false);
        });

        test('isOperationalWindowActive defaults to 24/7 on config error', () => {
            (fs.readFileSync as jest.Mock).mockImplementation(() => { throw new Error('File not found'); });
            expect(isOperationalWindowActive()).toBe(true);
        });

        test('isOperationalWindowActive returns true for 0-24 window', () => {
            (fs.readFileSync as jest.Mock).mockReturnValue(yaml.dump({ system: { operational_window: { start_hour_ist: 0, end_hour_ist: 24 } } }));
            expect(isOperationalWindowActive()).toBe(true);
        });
    });

    describe('circuit-breaker.ts', () => {
        test('CircuitBreaker transitions correctly', async () => {
            const breaker = new CircuitBreaker(2, 100);
            const successFn = jest.fn().mockResolvedValue('ok');
            const failFn = jest.fn().mockRejectedValue(new Error('fail'));

            // Closed -> Closed
            await expect(breaker.execute(successFn)).resolves.toBe('ok');
            expect(breaker.getState()).toBe(CircuitState.CLOSED);

            // Closed -> Open (2 failures)
            await expect(breaker.execute(failFn)).rejects.toThrow('fail');
            await expect(breaker.execute(failFn)).rejects.toThrow('fail');
            expect(breaker.getState()).toBe(CircuitState.OPEN);

            // Open -> Open (immediate reject)
            await expect(breaker.execute(successFn)).rejects.toThrow('Circuit breaker is OPEN');

            // Open -> Half-Open (after timeout)
            await new Promise(r => setTimeout(r, 150));
            await expect(breaker.execute(successFn)).resolves.toBe('ok');
            expect(breaker.getState()).toBe(CircuitState.CLOSED);
        });
    });

    describe('telegram_auth.ts', () => {
        test('OTP generation and verification', () => {
            const seed = 'test_seed';
            const otp = generateOTP(seed);
            expect(otp.length).toBe(8);
            expect(verifyOTP(seed, otp)).toBe(true);
            expect(verifyOTP(seed, 'wrong')).toBe(false);
            
            // Test window
            const oldOtp = generateOTP(seed, Math.floor(Date.now() / 1000) - 30);
            expect(verifyOTP(seed, oldOtp)).toBe(true);
        });
    });

    describe('passphrase.ts', () => {
        test('readPassphraseStdin works', async () => {
            const mockRl = {
                close: jest.fn(),
            };
            (readline.createInterface as jest.Mock).mockReturnValue(mockRl);

            const stdinOn = jest.spyOn(process.stdin, 'on');
            const stdoutWrite = jest.spyOn(process.stdout, 'write').mockImplementation(() => true);

            const promise = readPassphraseStdin('Prompt: ');
            
            // Find 'data' listener
            const dataListener = stdinOn.mock.calls.find(call => call[0] === 'data')![1] as (data: Buffer) => void;
            
            // Type 'secret'
            dataListener(Buffer.from('s'));
            dataListener(Buffer.from('e'));
            dataListener(Buffer.from('c'));
            dataListener(Buffer.from('r'));
            dataListener(Buffer.from('e'));
            dataListener(Buffer.from('t'));
            
            // Backspace then 't' again
            dataListener(Buffer.from([0x7f]));
            dataListener(Buffer.from('t'));

            // Enter
            dataListener(Buffer.from([0x0d]));

            await expect(promise).resolves.toBe('secret');
            expect(stdoutWrite).toHaveBeenCalledWith('Prompt: ');
            expect(mockRl.close).toHaveBeenCalled();
            
            stdoutWrite.mockRestore();
        });
    });

    describe('keystore.ts', () => {
        const tempPath = './temp_keystore.json';
        const passphrase = 'test_passphrase';
        const keypair = Keypair.generate();

        test('create and load keystore', async () => {
            let fileData = '';
            (fs.writeFileSync as jest.Mock).mockImplementation((path, data) => { fileData = data; });
            (fs.readFileSync as jest.Mock).mockImplementation(() => fileData);

            await createKeystore(keypair.secretKey, passphrase, tempPath);
            expect(fileData).toContain('encryptedSecretKey');

            const loadedKp = await loadKeypairFromKeystore(tempPath, passphrase);
            expect(loadedKp.publicKey.toBase58()).toBe(keypair.publicKey.toBase58());
            expect(Buffer.from(loadedKp.secretKey)).toEqual(Buffer.from(keypair.secretKey));
        });

        test('loadKeypairFromKeystore throws on wrong passphrase', async () => {
             // Mocking argon2 failure is hard without mocking the library
             // But we can verify the error path if we manipulate the fileData
             let fileData = '';
             (fs.writeFileSync as jest.Mock).mockImplementation((path, data) => { fileData = data; });
             (fs.readFileSync as jest.Mock).mockImplementation(() => fileData);

             await createKeystore(keypair.secretKey, passphrase, tempPath);
             
             await expect(loadKeypairFromKeystore(tempPath, 'wrong')).rejects.toThrow();
        });
    });

    describe('config_validator.ts', () => {
        const mockSchema = { type: 'object', properties: { test: { type: 'string' } } };
        const mockConfig = { test: 'value' };

        test('validateConfig returns true for valid config', () => {
            (fs.existsSync as jest.Mock).mockReturnValue(true);
            (fs.readFileSync as jest.Mock).mockReturnValue(JSON.stringify(mockSchema));
            
            const result = validateConfig(mockConfig);
            expect(result.isValid).toBe(true);
        });

        test('validateConfigFile handles YAML', () => {
            (fs.existsSync as jest.Mock).mockReturnValue(true);
            (fs.readFileSync as jest.Mock).mockImplementation((path: string) => {
                if (path.includes('schema')) return JSON.stringify(mockSchema);
                return yaml.dump(mockConfig);
            });
            
            const result = validateConfigFile('config.yaml');
            expect(result.isValid).toBe(true);
        });

        test('validateConfigAtStartup exits on error', () => {
            const exitSpy = jest.spyOn(process, 'exit').mockImplementation(() => { throw new Error('exit'); });
            (fs.existsSync as jest.Mock).mockReturnValue(true);
            (fs.readFileSync as jest.Mock)
                .mockReturnValueOnce(JSON.stringify(mockSchema))
                .mockReturnValueOnce('invalid: yaml: {'); // invalid yaml
            
            expect(() => validateConfigAtStartup('config.yaml')).toThrow('exit');
            expect(exitSpy).toHaveBeenCalledWith(1);
            exitSpy.mockRestore();
        });
    });
});
