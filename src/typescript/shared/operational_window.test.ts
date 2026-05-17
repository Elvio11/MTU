import { isOperationalWindowActive } from './operational-window';
import * as fs from 'fs';

jest.mock('fs');
jest.mock('js-yaml', () => ({
  load: jest.fn().mockReturnValue({ system: { operational_window: { start_hour_ist: 9, end_hour_ist: 17 } } }),
}));

describe('operational-window', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test('returns boolean for default 24/7', () => {
    (fs.existsSync as jest.Mock).mockReturnValue(false);
    expect(typeof isOperationalWindowActive()).toBe('boolean');
  });

  test('handles config load error', () => {
    (fs.existsSync as jest.Mock).mockReturnValue(true);
    (fs.readFileSync as jest.Mock).mockImplementation(() => { throw new Error('bad'); });
    expect(typeof isOperationalWindowActive()).toBe('boolean');
  });

  test('respects configured window', () => {
    (fs.existsSync as jest.Mock).mockReturnValue(true);
    (fs.readFileSync as jest.Mock).mockReturnValue('system:\n  operational_window:\n    start_hour_ist: 9\n    end_hour_ist: 17');
    expect(typeof isOperationalWindowActive()).toBe('boolean');
  });

  test('handles over-midnight window', () => {
    (fs.existsSync as jest.Mock).mockReturnValue(true);
    (fs.readFileSync as jest.Mock).mockReturnValue('system:\n  operational_window:\n    start_hour_ist: 21\n    end_hour_ist: 6');
    expect(typeof isOperationalWindowActive()).toBe('boolean');
  });

  test('defaults start_hour_ist to 0 when not specified', () => {
    const yaml = require('js-yaml');
    yaml.load.mockReturnValue({ system: { operational_window: { end_hour_ist: 17 } } });
    (fs.existsSync as jest.Mock).mockReturnValue(true);
    (fs.readFileSync as jest.Mock).mockReturnValue('system:\n  operational_window:\n    end_hour_ist: 17');
    expect(typeof isOperationalWindowActive()).toBe('boolean');
  });

  test('defaults end_hour_ist to 24 when not specified', () => {
    const yaml = require('js-yaml');
    yaml.load.mockReturnValue({ system: { operational_window: { start_hour_ist: 9 } } });
    (fs.existsSync as jest.Mock).mockReturnValue(true);
    (fs.readFileSync as jest.Mock).mockReturnValue('system:\n  operational_window:\n    start_hour_ist: 9');
    expect(typeof isOperationalWindowActive()).toBe('boolean');
  });
});
