import { Keypair } from '@solana/web3.js';
import * as fs from 'fs';

// Mock argon2 before anything else
jest.mock('argon2', () => ({
    argon2id: 2,
    hash: jest.fn(),
}));

jest.mock('fs');
jest.mock('sql.js', () => {
    return jest.fn().mockResolvedValue({
        Database: jest.fn().mockImplementation(() => ({
            exec: jest.fn().mockReturnValue([]),
            run: jest.fn(),
            export: jest.fn().mockReturnValue(new Uint8Array()),
            close: jest.fn(),
        }))
    });
});

describe('Shared Module Coverage', () => {
    let keystore: any;
    let db: any;
    let config_validator: any;
    let argon2: any;

    beforeAll(() => {
        // Require modules after mocks are set up
        keystore = require('./keystore');
        db = require('./db');
        config_validator = require('./config_validator');
        argon2 = require('argon2');
    });

    beforeEach(() => {
        jest.clearAllMocks();
    });

    describe('keystore.ts', () => {
        const passphrase = 'test-passphrase';
        const kPath = 'keystore.json';
        const kp = Keypair.generate();

        test('createKeystore saves encrypted key', async () => {
            (argon2.hash as jest.Mock).mockResolvedValue(Buffer.alloc(32));
            await keystore.createKeystore(kp.secretKey, passphrase, kPath);
            expect(fs.writeFileSync).toHaveBeenCalled();
        });

        test('loadKeypairFromKeystore decrypts correctly', async () => {
            (argon2.hash as jest.Mock).mockResolvedValue(Buffer.alloc(32));
            
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
            
            (fs.readFileSync as jest.Mock).mockReturnValue(JSON.stringify(mockData));

            const loadedKp = await keystore.loadKeypairFromKeystore(kPath, passphrase);
            expect(loadedKp.publicKey.toBase58()).toBe(kp.publicKey.toBase58());
        });
    });

    describe('config_validator.ts', () => {
        test('validateConfig works', () => {
            const validConfig = {
                solana: { rpc_url: 'http://localhost' },
                trading: { position_size_sol: 0.1 }
            };
            expect(() => config_validator.validateConfig(validConfig)).not.toThrow();
        });
    });

    describe('db.ts', () => {
        test('basic operations do not throw', () => {
            db.insertAuditLog.run({ event_type: 'test' });
            const pos = db.getOpenPositions.run();
            expect(Array.isArray(pos)).toBe(true);
        });

        test('shutdownDB cleans up', () => {
            expect(() => db.shutdownDB()).not.toThrow();
        });

        test('exportAuditLogToJSON works', () => {
            const result = db.exportAuditLogToJSON();
            expect(result).toBeNull(); // because mock db returns empty result
        });
    });
});
