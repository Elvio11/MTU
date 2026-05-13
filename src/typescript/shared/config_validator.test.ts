import * as fs from 'fs';
import * as path from 'path';
import { validateConfig, validateConfigFile, validateConfigAtStartup } from './config_validator';

jest.mock('fs');
jest.mock('ajv', () => {
  return jest.fn().mockImplementation(() => ({
    compile: jest.fn().mockReturnValue(jest.fn().mockReturnValue(true)),
  }));
});

describe('Config Validator', () => {
  const mockConfig = {
    trading: {
      positionSizeSOL: 0.1,
    }
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (fs.existsSync as jest.Mock).mockReturnValue(true);
    (fs.readFileSync as jest.Mock).mockImplementation((p: string) => {
      if (p.includes('schema')) return JSON.stringify({ type: 'object' });
      return JSON.stringify(mockConfig);
    });
  });

  test('validateConfig returns valid for correct config', () => {
    const result = validateConfig(mockConfig);
    expect(result.isValid).toBe(true);
  });

  test('validateConfig returns error if schema file missing', () => {
    (fs.existsSync as jest.Mock).mockReturnValue(false);
    const result = validateConfig(mockConfig);
    expect(result.isValid).toBe(false);
    expect(result.errors?.[0]).toContain('Schema file not found');
  });

  test('validateConfig returns error if schema is invalid JSON', () => {
    (fs.readFileSync as jest.Mock).mockImplementation((p: string) => {
      if (p.includes('config.schema.json')) return 'invalid json';
      return '';
    });
    const result = validateConfig(mockConfig);
    expect(result.isValid).toBe(false);
    expect(result.errors?.[0]).toContain('Failed to load schema');
  });

  test('validateConfigFile handles missing config file', () => {
    (fs.existsSync as jest.Mock).mockImplementation((p: string) => {
      if (p.includes('config.yaml')) return false;
      return true; // schema exists
    });
    const result = validateConfigFile('config.yaml');
    expect(result.isValid).toBe(false);
    expect(result.errors?.[0]).toContain('Config file not found');
  });

  test('validateConfigFile handles YAML-like content', () => {
    (fs.readFileSync as jest.Mock).mockImplementation((p: string) => {
      if (p.includes('schema')) return JSON.stringify({ type: 'object' });
      return 'trading:\n  tp1_multiplier: 2.0\n  # comment\n  tp2_multiplier: 3.0';
    });
    const result = validateConfigFile('config.yaml');
    expect(result.isValid).toBe(true);
  });

  test('validateConfigAtStartup exits on failure', () => {
    const exitSpy = jest.spyOn(process, 'exit').mockImplementation(() => { throw new Error('exit'); });
    (fs.existsSync as jest.Mock).mockReturnValue(false); // Schema missing
    
    expect(() => validateConfigAtStartup('config.yaml')).toThrow('exit');
    expect(exitSpy).toHaveBeenCalledWith(1);
    exitSpy.mockRestore();
  });

  test('validateConfigAtStartup logs success', () => {
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    validateConfigAtStartup('config.yaml');
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('Configuration is valid'));
    logSpy.mockRestore();
  });
});
