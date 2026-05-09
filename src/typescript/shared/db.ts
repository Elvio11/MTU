const fs = require('fs');
const path = require('path');

let db: any = null;
let SQL: any = null;
let dbPath: string | null = null;
let saveInterval: NodeJS.Timeout | null = null;

async function initDB(): Promise<boolean> {
  try {
    const initSqlJs = require('sql.js');
    SQL = await initSqlJs();
    
    dbPath = path.join(__dirname, '../../data/positions.db');
    
    let dbBuffer: Buffer | null = null;
    if (fs.existsSync(dbPath)) {
      try {
        dbBuffer = fs.readFileSync(dbPath);
        console.log('[DB] Loaded existing database');
      } catch (e) {
        console.log('[DB] Could not read existing db, creating new');
      }
    }
    
    db = new SQL.Database(dbBuffer);
    
    db.run(`
      CREATE TABLE IF NOT EXISTS positions (
        position_id TEXT PRIMARY KEY,
        mint TEXT NOT NULL,
        token_name TEXT,
        token_symbol TEXT,
        entry_price_sol REAL,
        entry_amount_sol REAL,
        tokens_received REAL,
        entry_tx_signature TEXT,
        entry_timestamp_utc TEXT,
        state TEXT NOT NULL,
        tp1_price REAL,
        tp2_price REAL,
        sl_price REAL,
        peak_price_sol REAL,
        exit_price_sol REAL,
        exit_tx_signature TEXT,
        realised_pnl_sol REAL,
        qualification_report TEXT,
        created_at TEXT,
        updated_at TEXT
      )
    `);
    
    db.run(`
      CREATE TABLE IF NOT EXISTS audit_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        envelope_id TEXT,
        agent_id TEXT,
        event_type TEXT,
        payload TEXT,
        timestamp_utc TEXT
      )
    `);
    
    console.log('[DB] SQLite (sql.js) initialized successfully');
    
    const dataDir = path.dirname(dbPath);
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
    
    saveInterval = setInterval(() => {
      if (db && dbPath) {
        try {
          const data = db.export();
          const buffer = Buffer.from(data);
          fs.writeFileSync(dbPath, buffer);
        } catch (e: any) {
          console.log('[DB] Auto-save error:', e.message);
        }
      }
    }, 30000);
    
    return true;
  } catch (e: any) {
    console.log('[DB] sql.js init failed:', e.message);
    return false;
  }
}

let dbReady = false;

initDB().then(() => {
  dbReady = true;
  console.log('[DB] Database ready');
}).catch(e => {
  console.log('[DB] Init failed:', e.message);
});

function saveDB(): boolean {
  if (!db || !dbPath) {
    console.log('[DB] Save skipped: DB not initialized');
    return false;
  }
  try {
    const data = db.export();
    const buffer = Buffer.from(data);
    fs.writeFileSync(dbPath, buffer);
    console.log('[DB] ✅ Saved to', dbPath);
    return true;
  } catch (e: any) {
    console.log('[DB] Save error:', e.message);
    return false;
  }
}

export const insertPosition = {
  run: function(params: any): void {
    if (!db || !dbReady) {
      console.log('[DB] insertPosition: DB not ready');
      return;
    }
    try {
      db.run(`
        INSERT OR REPLACE INTO positions (
          position_id, mint, token_name, token_symbol, entry_price_sol, entry_amount_sol,
          tokens_received, entry_tx_signature, entry_timestamp_utc, state, tp1_price,
          tp2_price, sl_price, peak_price_sol, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `, [
        params.position_id, params.mint, params.token_name || '', params.token_symbol || '',
        params.entry_price_sol || 0, params.entry_amount_sol || 0, params.tokens_received || 0,
        params.entry_tx_signature || '', params.entry_timestamp_utc || '', params.state || 'OPEN',
        params.tp1_price || 0, params.tp2_price || 0, params.sl_price || 0, 
        params.peak_price_sol || 0, params.created_at || new Date().toISOString(), 
        params.updated_at || new Date().toISOString()
      ]);
      saveDB();
    } catch (e: any) {
      console.log('[DB] insertPosition error:', e.message);
    }
  }
};

export const updatePosition = {
  run: function(params: any): void {
    if (!db || !dbReady) {
      console.log('[DB] updatePosition: DB not ready');
      return;
    }
    try {
      db.run(`
        UPDATE positions SET
          state = ?,
          peak_price_sol = ?,
          exit_price_sol = ?,
          exit_tx_signature = ?,
          realised_pnl_sol = ?,
          updated_at = ?
        WHERE position_id = ?
      `, [
        params.state || 'OPEN', 
        params.peak_price_sol || 0,
        params.exit_price_sol || 0,
        params.exit_tx_signature || '',
        params.realised_pnl_sol || 0,
        params.updated_at || new Date().toISOString(),
        params.position_id
      ]);
      saveDB();
    } catch (e: any) {
      console.log('[DB] updatePosition error:', e.message);
    }
  }
};

export const insertAuditLog = {
  run: function(params: any): void {
    if (!db) {
      console.log('[DB] insertAuditLog: DB not initialized');
      return;
    }
    try {
      db.run(`
        INSERT INTO audit_ledger (envelope_id, agent_id, event_type, payload, timestamp_utc)
        VALUES (?, ?, ?, ?, ?)
      `, [
        params.envelope_id || '',
        params.agent_id || '',
        params.event_type || '',
        typeof params.payload === 'string' ? params.payload : JSON.stringify(params.payload || {}),
        params.timestamp_utc || new Date().toISOString()
      ]);
      saveDB();
    } catch (e: any) {
      console.log('[DB] insertAuditLog error:', e.message);
    }
  }
};

export const getOpenPositions = {
  run: function(): any[] {
    if (!db || !dbReady) {
      console.log('[DB] getOpenPositions: DB not ready');
      return [];
    }
    try {
      const result = db.exec("SELECT * FROM positions WHERE state = 'OPEN'");
      if (result.length === 0 || result[0].values.length === 0) return [];
      
      const columns = result[0].columns;
      return result[0].values.map((row: any[]) => {
        const obj: any = {};
        columns.forEach((col: string, idx: number) => {
          obj[col] = row[idx];
        });
        return obj;
      });
    } catch (e: any) {
      console.log('[DB] getOpenPositions error:', e.message);
      return [];
    }
  }
};

export function exportAuditLogToJSON(outputPath?: string): string | null {
  if (!db) {
    console.log('[DB] exportAuditLog: DB not initialized');
    return null;
  }
  try {
    const result = db.exec('SELECT * FROM audit_ledger ORDER BY timestamp_utc DESC');
    if (result.length === 0 || result[0].values.length === 0) {
      console.log('[DB] exportAuditLog: No audit records found');
      return null;
    }
    
    const columns = result[0].columns;
    const records = result[0].values.map((row: any[]) => {
      const obj: any = {};
      columns.forEach((col: string, idx: number) => {
        obj[col] = row[idx];
      });
      try {
        obj.payload = JSON.parse(obj.payload);
      } catch {}
      return obj;
    });
    
    const exportData = {
      exported_at: new Date().toISOString(),
      total_records: records.length,
      records: records
    };
    
    const exportPath = outputPath || path.join(__dirname, '../../data/audit_export.json');
    fs.writeFileSync(exportPath, JSON.stringify(exportData, null, 2));
    console.log(`[DB] ✅ Audit export: ${records.length} records → ${exportPath}`);
    return exportPath;
  } catch (e: any) {
    console.log('[DB] exportAuditLog error:', e.message);
    return null;
  }
}

setInterval(() => {
  const dataDir = path.join(__dirname, '../../data');
  if (!fs.existsSync(dataDir)) return;
  const exportPath = path.join(dataDir, 'audit_daily.json');
  exportAuditLogToJSON(exportPath);
}, 24 * 60 * 60 * 1000);