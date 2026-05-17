import { validateConfig, validateConfigAtStartup } from './config_validator';

jest.mock('fs');

describe('Config Validator', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        const fs = require('fs');
        fs.existsSync.mockReturnValue(true);
        fs.readFileSync.mockReturnValue(JSON.stringify({ type: 'object' }));
    });

    test('validateConfig returns valid for correct config', () => {
        const result = validateConfig({ trading: { positionSizeSOL: 0.1 } });
        expect(result.isValid).toBe(true);
    });

    test('validateConfigAtStartup throws when schema missing', () => {
        const fs = require('fs');
        fs.existsSync.mockReturnValue(false);
        const exitSpy = jest.spyOn(process, 'exit').mockImplementation((() => { throw new Error('exit'); }) as any);
        expect(() => validateConfigAtStartup('config.yaml')).toThrow('exit');
        expect(exitSpy).toHaveBeenCalledWith(1);
        exitSpy.mockRestore();
    });

    test('validateConfigAtStartup succeeds', () => {
        const logSpy = jest.spyOn(console, 'log').mockImplementation();
        validateConfigAtStartup('config.yaml');
        expect(logSpy).toHaveBeenCalled();
        logSpy.mockRestore();
    });

  test('validateConfig handles AJV errors', () => {
    jest.isolateModules(() => {
      const fs = require('fs');
      fs.readFileSync.mockReturnValue('invalid json');
      const { validateConfig: vc } = require('./config_validator');
      const result = vc({});
      expect(result.isValid).toBe(false);
    });
  });

  test('validateConfig handles AJV compile error', () => {
    jest.isolateModules(() => {
      const fs = require('fs');
      fs.readFileSync.mockReturnValue(JSON.stringify({ type: 'nonexistent' }));
      const { validateConfig: vc } = require('./config_validator');
      const result = vc({});
      expect(result.isValid).toBe(false);
    });
  });

  test('validateConfigFile handles read error', () => {
    jest.isolateModules(() => {
      const fs = require('fs');
      fs.readFileSync.mockImplementation(() => { throw new Error('read failed'); });
      const { validateConfigFile } = require('./config_validator');
      const result = validateConfigFile('config.yaml');
      expect(result.isValid).toBe(false);
    });
  });
});
