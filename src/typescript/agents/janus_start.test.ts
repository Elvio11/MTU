jest.mock('./janus');
jest.mock('../shared/passphrase');

describe('janus_start Entry Point', () => {
    let exitSpy: jest.SpyInstance;

    beforeEach(() => {
        jest.resetModules();
        jest.clearAllMocks();
        exitSpy = jest.spyOn(process, 'exit').mockImplementation((() => { throw new Error('Process.exit'); }) as any);
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
        const mockAgent = { init: jest.fn().mockResolvedValue(undefined), loadWallets: jest.fn().mockResolvedValue(undefined), run: jest.fn().mockResolvedValue(undefined), stop: jest.fn() };
        JanusAgent.mockImplementation(() => mockAgent);
        readPassphraseStdin.mockResolvedValue('user-pass');
        const { janusMain } = require('./janus_start');
        await janusMain();
        expect(mockAgent.loadWallets).toHaveBeenCalledWith('user-pass', 'user-pass');
        expect(mockAgent.run).toHaveBeenCalled();
    });

    test('fails if wallet load fails', async () => {
        const { JanusAgent } = require('./janus');
        const mockAgent = { init: jest.fn().mockResolvedValue(undefined), loadWallets: jest.fn().mockRejectedValue(new Error('Decrypt fail')), run: jest.fn() };
        JanusAgent.mockImplementation(() => mockAgent);
        const { janusMain } = require('./janus_start');
        try { await janusMain(); } catch (e) {}
        expect(exitSpy).toHaveBeenCalledWith(1);
    });

    test('handles init failure', async () => {
        const { JanusAgent } = require('./janus');
        const mockAgent = { init: jest.fn().mockRejectedValue(new Error('init failed')), loadWallets: jest.fn(), run: jest.fn() };
        JanusAgent.mockImplementation(() => mockAgent);
        const { janusMain } = require('./janus_start');
        try { await janusMain(); } catch (e) {}
        expect(exitSpy).toHaveBeenCalledWith(1);
    });

    test('handles init failure', async () => {
        const { JanusAgent } = require('./janus');
        const mockAgent = { init: jest.fn().mockRejectedValue(new Error('init failed')), loadWallets: jest.fn(), run: jest.fn() };
        JanusAgent.mockImplementation(() => mockAgent);
        const { janusMain } = require('./janus_start');
        try { await janusMain(); } catch (e) {}
        expect(exitSpy).toHaveBeenCalledWith(1);
    });
});
