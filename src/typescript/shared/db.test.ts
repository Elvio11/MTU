jest.mock('fs');

let mockDbInstance: { run: jest.Mock; exec: jest.Mock; export: jest.Mock } | null = null;

jest.mock('sql.js', () => {
  const Database = jest.fn().mockImplementation(() => {
    const db = {
      run: jest.fn(),
      exec: jest.fn().mockReturnValue([{ columns: ['id', 'payload'], values: [[1, '{}']] }]),
      export: jest.fn().mockReturnValue(new Uint8Array([1, 2, 3])),
    };
    mockDbInstance = db;
    return db;
  });
  return jest.fn().mockImplementation(() => Promise.resolve({ Database }));
});

describe('Database', () => {
  beforeEach(async () => {
    mockDbInstance = null;
    jest.resetModules();
    jest.clearAllMocks();
    jest.useFakeTimers();
    const fs = require('fs');
    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(Buffer.from([1, 2, 3]));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('initDB initializes database successfully', async () => {
    const { initDB } = require('./db');
    const success = await initDB();
    expect(success).toBe(true);
  });

  test('initDB handles missing db file', async () => {
    const fs = require('fs');
    fs.existsSync.mockReturnValue(false);
    const { initDB } = require('./db');
    const success = await initDB();
    expect(success).toBe(true);
  });

  test('initDB handles readFileSync error', async () => {
    const fs = require('fs');
    fs.readFileSync.mockImplementation(() => { throw new Error('read error'); });
    const { initDB } = require('./db');
    const success = await initDB();
    expect(success).toBe(true);
  });

  test('initDB handles sql.js failure', async () => {
    const sqlJs = require('sql.js');
    sqlJs.mockRejectedValueOnce(new Error('sql init failed'));
    const { initDB } = require('./db');
    const success = await initDB();
    expect(success).toBe(false);
  });

  test('insertPosition saves a position', async () => {
    await require('./db').initDB();
    const { insertPosition } = require('./db');
    insertPosition.run({ position_id: 'p1', mint: 'mint123' });
    const fs = require('fs');
    expect(fs.writeFileSync).toHaveBeenCalled();
  });

  test('insertPosition handles db not ready', () => {
    jest.isolateModules(() => {
      const { insertPosition } = require('./db');
      const logSpy = jest.spyOn(console, 'log').mockImplementation();
      insertPosition.run({ position_id: 'p1' });
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('DB not ready'));
      logSpy.mockRestore();
    });
  });

  test('insertPosition handles run error', async () => {
    await require('./db').initDB();
    mockDbInstance!.run.mockImplementation(() => { throw new Error('insert error'); });
    const { insertPosition } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    insertPosition.run({ position_id: 'p1' });
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('insertPosition error'), expect.stringContaining('insert error'));
    logSpy.mockRestore();
  });

  test('updatePosition handles db not ready', () => {
    jest.isolateModules(() => {
      const { updatePosition } = require('./db');
      const logSpy = jest.spyOn(console, 'log').mockImplementation();
      updatePosition.run({ position_id: 'p1' });
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('DB not ready'));
      logSpy.mockRestore();
    });
  });

  test('insertAuditLog handles no db', () => {
    jest.isolateModules(() => {
      const { insertAuditLog } = require('./db');
      const logSpy = jest.spyOn(console, 'log').mockImplementation();
      insertAuditLog.run({ agent_id: 'ares' });
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('DB not initialized'));
      logSpy.mockRestore();
    });
  });

  test('getOpenPositions returns positions', async () => {
    await require('./db').initDB();
    const { getOpenPositions } = require('./db');
    const positions = getOpenPositions.run();
    expect(positions.length).toBeGreaterThan(0);
  });

  test('getOpenPositions handles db not ready', () => {
    jest.isolateModules(() => {
      const { getOpenPositions } = require('./db');
      const result = getOpenPositions.run();
      expect(result).toEqual([]);
    });
  });

  test('exportAuditLogToJSON handles no db', () => {
    jest.isolateModules(() => {
      const { exportAuditLogToJSON } = require('./db');
      const result = exportAuditLogToJSON();
      expect(result).toBeNull();
    });
  });

  test('shutdownDB clears intervals', async () => {
    await require('./db').initDB();
    const { shutdownDB } = require('./db');
    const clearSpy = jest.spyOn(global, 'clearInterval');
    shutdownDB();
    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });

  test('updatePosition handles run error', async () => {
    await require('./db').initDB();
    mockDbInstance!.run.mockImplementation(() => { throw new Error('update error'); });
    const { updatePosition } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    updatePosition.run({ position_id: 'p1' });
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('updatePosition error'), expect.stringContaining('update error'));
    logSpy.mockRestore();
  });

  test('insertAuditLog handles run error', async () => {
    await require('./db').initDB();
    mockDbInstance!.run.mockImplementation(() => { throw new Error('audit error'); });
    const { insertAuditLog } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    insertAuditLog.run({ envelope_id: 'e1', agent_id: 'ares', event_type: 'test', payload: {} });
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('insertAuditLog error'), expect.stringContaining('audit error'));
    logSpy.mockRestore();
  });

  test('getOpenPositions handles exec error', async () => {
    await require('./db').initDB();
    mockDbInstance!.exec.mockImplementation(() => { throw new Error('exec error'); });
    const { getOpenPositions } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const result = getOpenPositions.run();
    expect(result).toEqual([]);
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('getOpenPositions error'), expect.stringContaining('exec error'));
    logSpy.mockRestore();
  });

  test('exportAuditLogToJSON handles empty results', async () => {
    await require('./db').initDB();
    mockDbInstance!.exec.mockReturnValue([]);
    const { exportAuditLogToJSON } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const result = exportAuditLogToJSON();
    expect(result).toBeNull();
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('No audit records found'));
    logSpy.mockRestore();
  });

  test('exportAuditLogToJSON handles empty values', async () => {
    await require('./db').initDB();
    mockDbInstance!.exec.mockReturnValue([{ columns: ['id'], values: [] }]);
    const { exportAuditLogToJSON } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const result = exportAuditLogToJSON();
    expect(result).toBeNull();
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('No audit records found'));
    logSpy.mockRestore();
  });

  test('exportAuditLogToJSON handles write error', async () => {
    await require('./db').initDB();
    const fs = require('fs');
    fs.writeFileSync.mockImplementation(() => { throw new Error('write error'); });
    const { exportAuditLogToJSON } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    const result = exportAuditLogToJSON('/tmp/test.json');
    expect(result).toBeNull();
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('exportAuditLog error'), expect.stringContaining('write error'));
    logSpy.mockRestore();
  });

  test('saveDB handles export error via insertPosition', async () => {
    await require('./db').initDB();
    mockDbInstance!.export.mockImplementation(() => { throw new Error('save error'); });
    const { insertPosition } = require('./db');
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    insertPosition.run({ position_id: 'p1', mint: 'mint123' });
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('Save error'), expect.stringContaining('save error'));
    logSpy.mockRestore();
  });

  test('auto-save interval saves on tick', async () => {
    const fs = require('fs');
    await require('./db').initDB();
    jest.advanceTimersByTime(30000);
    expect(fs.writeFileSync).toHaveBeenCalled();
  });

  test('auto-save interval handles export error', async () => {
    await require('./db').initDB();
    mockDbInstance!.export.mockImplementation(() => { throw new Error('export error'); });
    const logSpy = jest.spyOn(console, 'log').mockImplementation();
    jest.advanceTimersByTime(30000);
    expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('Auto-save error'), expect.stringContaining('export error'));
    logSpy.mockRestore();
  });
});
