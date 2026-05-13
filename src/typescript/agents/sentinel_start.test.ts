import * as passphrase from '../shared/passphrase';

jest.mock('./sentinel');
jest.mock('../shared/passphrase');
jest.mock('../shared/config_validator', () => ({
    validateConfigAtStartup: jest.fn()
}));

describe('sentinel_start Entry Point', () => {
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

    test('successfully starts sentinel agent', async () => {
        const { SentinelAgent } = require('./sentinel');
        const { readPassphraseStdin } = require('../shared/passphrase');
        
        const mockAgentInstance = {
            loadKeypair: jest.fn().mockResolvedValue(undefined),
            run: jest.fn().mockResolvedValue(undefined),
            stop: jest.fn()
        };
        SentinelAgent.mockImplementation(() => mockAgentInstance);
        readPassphraseStdin.mockResolvedValue('user-pass');

        const { sentinelMain } = require('./sentinel_start');
        await sentinelMain();

        expect(mockAgentInstance.loadKeypair).toHaveBeenCalledWith('user-pass');
        expect(mockAgentInstance.run).toHaveBeenCalled();
    });

    test('fails if wallet load fails', async () => {
        const { SentinelAgent } = require('./sentinel');
        const mockAgentInstance = {
            loadKeypair: jest.fn().mockRejectedValue(new Error('Decrypt fail')),
            run: jest.fn(),
        };
        SentinelAgent.mockImplementation(() => mockAgentInstance);

        const { sentinelMain } = require('./sentinel_start');
        try {
            await sentinelMain();
        } catch (e) {}

        expect(exitSpy).toHaveBeenCalledWith(1);
    });
});
