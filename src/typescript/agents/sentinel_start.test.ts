jest.mock('./sentinel');
jest.mock('../shared/passphrase');

describe('sentinel_start Entry Point', () => {
    let exitSpy: jest.SpyInstance;

    beforeEach(() => {
        jest.resetModules();
        jest.clearAllMocks();
        exitSpy = jest.spyOn(process, 'exit').mockImplementation((() => { throw new Error('Process.exit'); }) as any);
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
        const mockAgent = { init: jest.fn().mockResolvedValue(undefined), loadKeypair: jest.fn().mockResolvedValue(undefined), run: jest.fn().mockResolvedValue(undefined), stop: jest.fn() };
        SentinelAgent.mockImplementation(() => mockAgent);
        readPassphraseStdin.mockResolvedValue('user-pass');
        const { sentinelMain } = require('./sentinel_start');
        await sentinelMain();
        expect(mockAgent.loadKeypair).toHaveBeenCalledWith('user-pass');
        expect(mockAgent.run).toHaveBeenCalled();
    });

    test('fails if wallet load fails', async () => {
        const { SentinelAgent } = require('./sentinel');
        const mockAgent = { init: jest.fn().mockResolvedValue(undefined), loadKeypair: jest.fn().mockRejectedValue(new Error('Decrypt fail')), run: jest.fn() };
        SentinelAgent.mockImplementation(() => mockAgent);
        const { sentinelMain } = require('./sentinel_start');
        try { await sentinelMain(); } catch (e) {}
        expect(exitSpy).toHaveBeenCalledWith(1);
    });

    test('exits if no passphrase available', async () => {
        const { SentinelAgent } = require('./sentinel');
        const mockAgent = { init: jest.fn().mockResolvedValue(undefined), loadKeypair: jest.fn(), run: jest.fn() };
        SentinelAgent.mockImplementation(() => mockAgent);
        (process.stdin as any).isTTY = false;
        delete process.env.SNIPER_PASSPHRASE;
        const { sentinelMain } = require('./sentinel_start');
        try { await sentinelMain(); } catch (e) {}
        expect(exitSpy).toHaveBeenCalledWith(1);
    });

    test('handles init failure', async () => {
        const { SentinelAgent } = require('./sentinel');
        const mockAgent = { init: jest.fn().mockRejectedValue(new Error('init failed')), loadKeypair: jest.fn(), run: jest.fn() };
        SentinelAgent.mockImplementation(() => mockAgent);
        const { sentinelMain } = require('./sentinel_start');
        try { await sentinelMain(); } catch (e) {}
        expect(exitSpy).toHaveBeenCalledWith(1);
    });
});
