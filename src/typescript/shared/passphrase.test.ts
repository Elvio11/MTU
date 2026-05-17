import { readPassphraseStdin } from './passphrase';
import * as readline from 'readline';

jest.mock('readline');

describe('passphrase', () => {
  let mockOn: jest.Mock;
  let mockWrite: jest.Mock;
  let originalStdinOn: any;
  let originalStdoutWrite: any;

  beforeEach(() => {
    mockOn = jest.fn();
    mockWrite = jest.fn();
    originalStdinOn = process.stdin.on;
    originalStdoutWrite = process.stdout.write;
    process.stdin.on = mockOn as any;
    process.stdout.write = mockWrite as any;
    (process.stdin as any).isTTY = true;
    (process.stdin as any).setRawMode = jest.fn();
  });

  afterEach(() => {
    process.stdin.on = originalStdinOn;
    process.stdout.write = originalStdoutWrite;
  });

  test('reads passphrase with masking', async () => {
    (readline.createInterface as jest.Mock).mockReturnValue({ close: jest.fn() });
    const promise = readPassphraseStdin('Enter: ');
    const dataCb = mockOn.mock.calls.find((c: any) => c[0] === 'data')![1];
    dataCb(Buffer.from([0x61]));
    dataCb(Buffer.from([0x62]));
    dataCb(Buffer.from([0x0d]));
    expect(await promise).toBe('ab');
    expect(mockWrite).toHaveBeenCalledWith('*');
  });

  test('handles backspace', async () => {
    (readline.createInterface as jest.Mock).mockReturnValue({ close: jest.fn() });
    const promise = readPassphraseStdin();
    const dataCb = mockOn.mock.calls.find((c: any) => c[0] === 'data')![1];
    dataCb(Buffer.from([0x61]));
    dataCb(Buffer.from([0x62]));
    dataCb(Buffer.from([0x7f]));
    dataCb(Buffer.from([0x0d]));
    expect(await promise).toBe('a');
  });

  test('handles stdin error', async () => {
    (readline.createInterface as jest.Mock).mockReturnValue({ close: jest.fn() });
    const promise = readPassphraseStdin();
    const errorCb = mockOn.mock.calls.find((c: any) => c[0] === 'error')![1];
    errorCb(new Error('stream error'));
    await expect(promise).rejects.toThrow('stream error');
  });

  test('handles non-TTY stdin', async () => {
    (process.stdin as any).isTTY = false;
    (readline.createInterface as jest.Mock).mockReturnValue({ close: jest.fn() });
    const promise = readPassphraseStdin();
    const dataCb = mockOn.mock.calls.find((c: any) => c[0] === 'data')![1];
    dataCb(Buffer.from([0x61]));
    dataCb(Buffer.from([0x0a]));
    expect(await promise).toBe('a');
  });

  test('handles backspace with empty buffer', async () => {
    (readline.createInterface as jest.Mock).mockReturnValue({ close: jest.fn() });
    const promise = readPassphraseStdin();
    const dataCb = mockOn.mock.calls.find((c: any) => c[0] === 'data')![1];
    dataCb(Buffer.from([0x08]));
    dataCb(Buffer.from([0x0d]));
    expect(await promise).toBe('');
  });
});
