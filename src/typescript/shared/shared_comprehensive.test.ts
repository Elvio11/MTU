import { Keypair } from '@solana/web3.js';

describe('Shared Module Comprehensive Coverage', () => {
    let keystore: any;
    let db: any;
    let config_validator: any;
    let argon2: any;
    let fs: any;

    beforeEach(() => {
        jest.resetModules();
        jest.clearAllMocks();

        // Mock fs
        jest.mock('fs', () => ({
            readFileSync: jest.fn(),
            writeFileSync: jest.fn(),
            existsSync: jest.fn(),
            mkdirSync: jest.fn(),
        }));
        fs = require('fs');

        // Mock argon2
        jest.mock('argon2', () => ({
            argon2id: 2,
            hash: jest.fn(),
        }));
        argon2 = require('argon2');

        // Mock sql.js
        const mockDb = {
            exec: jest.fn().mockReturnValue([]),
            run: jest.fn(),
            export: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3])),
            close: jest.fn(),
        };
        jest.mock('sql.js', () => {
            return jest.fn().mockResolvedValue({
                Database: jest.fn().mockImplementation(() => mockDb)
            });
        });
        // Set NODE_ENV to test to avoid auto-init logic in db.ts
        process.env.NODE_ENV = 'test';

        // Require modules after mocks are set up
        keystore = require('./keystore');
        db = require('./db');
        config_validator = require('./config_validator');
        (db as any).mockDb = mockDb; // Hack to access it in tests
    });

    describe('keystore.ts', () => {
        const passphrase = 'test-passphrase';
        const kPath = 'keystore.json';
        const kp = Keypair.generate();

        test('createKeystore saves encrypted key', async () => {
            argon2.hash.mockResolvedValue(Buffer.alloc(32));
            await keystore.createKeystore(kp.secretKey, passphrase, kPath);
            expect(fs.writeFileSync).toHaveBeenCalled();
        });

        test('loadKeypairFromKeystore decrypts correctly', async () => {
            argon2.hash.mockResolvedValue(Buffer.alloc(32));
            
            const salt = Buffer.alloc(16);
            const key = Buffer.alloc(32);
            const nonce = Buffer.alloc(24);
            const encrypted = require('tweetnacl').secretbox(kp.secretKey, nonce, key);
            
            const mockData = {
                salt: salt.toString('hex'),
                nonce: nonce.toString('hex'),
                encryptedSecretKey: Buffer.from(encrypted).toString('hex'),
                kdfParams: {}
            };
            
            fs.readFileSync.mockReturnValue(JSON.stringify(mockData));

            const loadedKp = await keystore.loadKeypairFromKeystore(kPath, passphrase);
            expect(loadedKp.publicKey.toBase58()).toBe(kp.publicKey.toBase58());
        });

        test('loadKeypairFromKeystore throws on invalid passphrase', async () => {
            argon2.hash.mockResolvedValue(Buffer.alloc(32).fill(1)); // Wrong key
            
            const mockData = {
                salt: Buffer.alloc(16).toString('hex'),
                nonce: Buffer.alloc(24).toString('hex'),
                encryptedSecretKey: Buffer.alloc(32).toString('hex'),
                kdfParams: {}
            };
            
            fs.readFileSync.mockReturnValue(JSON.stringify(mockData));

            await expect(keystore.loadKeypairFromKeystore(kPath, passphrase))
                .rejects.toThrow('Invalid passphrase or corrupted keystore');
        });
    });

    describe('db.ts', () => {
        test('insertPosition handles DB not ready', () => {
            const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
            db.insertPosition.run({});
            expect(consoleSpy).toHaveBeenCalledWith('[DB] insertPosition: DB not ready');
            consoleSpy.mockRestore();
        });

        describe('Initialized DB', () => {
            beforeEach(async () => {
                fs.readFileSync.mockReturnValue(new Uint8Array([1, 2, 3]));
                await db.initDB();
            });

            test('updatePosition updates record', () => {
                db.updatePosition.run({
                    position_id: 'p1',
                    state: 'CLOSED',
                    peak_price_sol: 0.2
                });
                expect(fs.writeFileSync).toHaveBeenCalled();
            });

            test('insertAuditLog adds record', () => {
                db.insertAuditLog.run({
                    envelope_id: 'env1',
                    agent_id: 'sentinel',
                    event_type: 'TP1',
                    payload: { test: true }
                });
                expect(fs.writeFileSync).toHaveBeenCalled();
            });

            test('getOpenPositions returns positions', async () => {
                const result = db.getOpenPositions.run();
                expect(Array.isArray(result)).toBe(true);
            });

            test('exportAuditLogToJSON returns path', () => {
                const mockDb = (db as any).mockDb;
                mockDb.exec.mockReturnValueOnce([{
                    columns: ['id', 'payload'],
                    values: [[1, '{"test":true}']]
                }]);
                
                const path = db.exportAuditLogToJSON('test.json');
                expect(path).toBe('test.json');
                expect(fs.writeFileSync).toHaveBeenCalledWith('test.json', expect.stringContaining('"test": true'));
            });
        });
    });

    describe('config_validator.ts', () => {
        test('validateConfig handles missing schema', () => {
            fs.existsSync.mockReturnValue(false);
            const result = config_validator.validateConfig({});
            expect(result.isValid).toBe(false);
        });
    });

    describe('operational-window.ts', () => {
        let opWindow: any;
        beforeEach(() => {
            opWindow = require('./operational-window');
        });

        test('isOperationalWindowActive returns true for default 24/7', () => {
            fs.readFileSync.mockReturnValue('system: { operational_window: { start_hour_ist: 0, end_hour_ist: 24 } }');
            expect(opWindow.isOperationalWindowActive()).toBe(true);
        });

        test('isOperationalWindowActive handles over-midnight window', () => {
            // Mock IST hour to be 22 (inside 21-06 window)
            const { DateTime } = require('luxon');
            const originalNow = DateTime.utc;
            DateTime.utc = jest.fn().mockReturnValue(DateTime.fromObject({ hour: 17 }, { zone: 'UTC' })); // 17 UTC is 22:30 IST
            
            fs.readFileSync.mockReturnValue('system: { operational_window: { start_hour_ist: 21, end_hour_ist: 6 } }');
            expect(opWindow.isOperationalWindowActive()).toBe(true);
            
            DateTime.utc = originalNow;
        });
    });
});
