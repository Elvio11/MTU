import * as passphrase from '../shared/passphrase';

jest.mock('./ares');
jest.mock('../shared/passphrase');
jest.mock('../shared/config_validator', () => ({
    validateConfigAtStartup: jest.fn()
}));

describe('ares_start Entry Point', () => {
    let exitSpy: jest.SpyInstance;

    beforeEach(() => {
        jest.resetModules();
        jest.clearAllMocks();
        
        exitSpy = jest.spyOn(process, 'exit').mockImplementation((code?: string | number | null | undefined): never => {
            throw new Error(`Process.exit called with ${code}`);
        });
        
        process.env.SNIPER_PASSPHRASE = 'test-pass';
        (process.stdin as any).isTTY = true;
        delete process.env.PM2_HOME;
    });

    afterEach(() => {
        exitSpy.mockRestore();
    });

    test('successfully starts agent', async () => {
        const { AresAgent } = require('./ares');
        const { readPassphraseStdin } = require('../shared/passphrase');
        
        const mockAgentInstance = {
            init: jest.fn().mockResolvedValue(undefined),
            loadSniperWallet: jest.fn().mockResolvedValue(undefined),
            run: jest.fn().mockResolvedValue(undefined),
            stop: jest.fn()
        };
        AresAgent.mockImplementation(() => mockAgentInstance);
        readPassphraseStdin.mockResolvedValue('user-pass');

        const { aresMain } = require('./ares_start');
        await aresMain();

        expect(AresAgent).toHaveBeenCalled();
        expect(mockAgentInstance.loadSniperWallet).toHaveBeenCalledWith('user-pass');
        expect(mockAgentInstance.run).toHaveBeenCalled();
    });

    test('fails if wallet load fails', async () => {
        const { AresAgent } = require('./ares');
        const mockAgentInstance = {
            init: jest.fn().mockResolvedValue(undefined),
            loadSniperWallet: jest.fn().mockRejectedValue(new Error('Decrypt fail')),
            run: jest.fn(),
        };
        AresAgent.mockImplementation(() => mockAgentInstance);

        const { aresMain } = require('./ares_start');
        try {
            await aresMain();
        } catch (e) {}

        expect(exitSpy).toHaveBeenCalledWith(1);
    });

    test('uses env var passphrase when not TTY', async () => {
        const { AresAgent } = require('./ares');
        const mockAgentInstance = {
            init: jest.fn().mockResolvedValue(undefined),
            loadSniperWallet: jest.fn().mockResolvedValue(undefined),
            run: jest.fn(),
        };
        AresAgent.mockImplementation(() => mockAgentInstance);
        process.env.SNIPER_PASSPHRASE = 'env-pass';
        (process.stdin as any).isTTY = false;
        process.env.PM2_HOME = 'true';

        const { aresMain } = require('./ares_start');
        await aresMain();

        expect(mockAgentInstance.loadSniperWallet).toHaveBeenCalledWith('env-pass');
    });
});
