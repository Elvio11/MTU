import { initDB, insertPosition, updatePosition, insertAuditLog, getOpenPositions, exportAuditLogToJSON, shutdownDB } from './db';
import * as fs from 'fs';
import * as path from 'path';

jest.mock('fs');

describe('Database Module Rigorous Tests', () => {
    beforeAll(async () => {
        (fs.existsSync as jest.Mock).mockReturnValue(false);
        await initDB();
    });

    afterAll(() => {
        shutdownDB();
    });

    beforeEach(() => {
        jest.clearAllMocks();
    });

    test('insertPosition and getOpenPositions', () => {
        const pos = {
            position_id: 'pos1',
            mint: 'mint1',
            state: 'OPEN',
            entry_price_sol: 0.1,
            tokens_received: 100
        };

        insertPosition.run(pos);
        
        const open = getOpenPositions.run();
        expect(open.length).toBe(1);
        expect(open[0].position_id).toBe('pos1');
        expect(open[0].mint).toBe('mint1');
    });

    test('updatePosition updates state', () => {
        updatePosition.run({
            position_id: 'pos1',
            state: 'CLOSED',
            exit_price_sol: 0.15,
            realised_pnl_sol: 0.05
        });

        const open = getOpenPositions.run();
        expect(open.length).toBe(0);
    });

    test('insertAuditLog and exportAuditLogToJSON', () => {
        const log = {
            envelope_id: 'env1',
            agent_id: 'agent1',
            event_type: 'trade',
            payload: { data: 'test' }
        };

        insertAuditLog.run(log);

        let fileWritten = false;
        (fs.writeFileSync as jest.Mock).mockImplementation(() => { fileWritten = true; });

        const result = exportAuditLogToJSON('./test_export.json');
        expect(result).toBe('./test_export.json');
        expect(fileWritten).toBe(true);
    });

    test('getOpenPositions returns empty array on error or no data', () => {
        // Already tested empty case above after updatePosition
        const open = getOpenPositions.run();
        expect(open).toEqual([]);
    });

    test('initDB handles existing database file', async () => {
        (fs.existsSync as jest.Mock).mockReturnValue(true);
        (fs.readFileSync as jest.Mock).mockReturnValue(Buffer.from([]));
        
        // This will try to load empty buffer as DB, might fail or create new
        const success = await initDB();
        expect(success).toBe(true);
    });

    test('initDB handles missing data directory', async () => {
        (fs.existsSync as jest.Mock).mockImplementation((p) => {
            if (p.includes('positions.db')) return false;
            if (p.includes('data')) return false;
            return true;
        });
        (fs.mkdirSync as jest.Mock).mockImplementation(() => true);

        await initDB();
        expect(fs.mkdirSync).toHaveBeenCalled();
    });
});
