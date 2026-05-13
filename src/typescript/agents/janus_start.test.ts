import * as passphrase from '../shared/passphrase';

jest.mock('./janus');
jest.mock('../shared/passphrase');
jest.mock('../shared/config_validator', () => ({
    validateConfigAtStartup: jest.fn()
}));

describe('janus_start Entry Point', () => {
    let exitSpy: jest.SpyInstance;

    beforeEach(() => {
        jest.resetModules();
        jest.clearAllMocks();
        exitSpy = jest.spyOn(process, 'exit').mockImplementation((code?: string | number | null | undefined): never => {
            throw new Error(`Process.exit called with ${code}`);
        });
        
        process.env.SNIPER_PASSPHRASE = 'test-pass';
        process.env.MAIN_PASSPHRASE = 'test-pass-2';
        (process.stdin as any).isTTY = true;
        delete process.env.PM2_HOME;
    });

    afterEach(() => {
        exitSpy.mockRestore();
    });

    test('successfully starts janus agent', async () => {
        const { JanusAgent } = require('./janus');
        const { readPassphraseStdin } = require('../shared/passphrase');
        
        const mockAgentInstance = {
            loadWallets: jest.fn().mockResolvedValue(undefined),
            run: jest.fn().mockResolvedValue(undefined),
            stop: jest.fn()
        };
        JanusAgent.mockImplementation(() => mockAgentInstance);
        readPassphraseStdin.mockResolvedValue('user-pass');

        const { janusMain } = require('./janus_start');
        await janusMain();

        expect(mockAgentInstance.loadWallets).toHaveBeenCalledWith('user-pass', 'user-pass');
        expect(mockAgentInstance.run).toHaveBeenCalled();
    });

    test('fails if wallet load fails', async () => {
        const { JanusAgent } = require('./janus');
        const mockAgentInstance = {
            loadWallets: jest.fn().mockRejectedValue(new Error('Decrypt fail')),
            run: jest.fn(),
        };
        JanusAgent.mockImplementation(() => mockAgentInstance);

        const { janusMain } = require('./janus_start');
        try {
            await janusMain();
        } catch (e) {}

        expect(exitSpy).toHaveBeenCalledWith(1);
    });
});
