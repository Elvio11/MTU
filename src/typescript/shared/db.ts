/**
 * db.ts — PostgreSQL-backed persistence layer for MTUS.
 * Replaces the previous sql.js (in-memory SQLite) implementation.
 * Uses the `pg` (node-postgres) library with a connection pool for
 * safe concurrent access from multiple agents.
 */

import { Pool, PoolClient } from 'pg';

// ─── Connection Pool ──────────────────────────────────────────────────────────

const DATABASE_URL =
  process.env.DATABASE_URL ||
  `postgresql://${process.env.DB_USER || 'postgres'}:${process.env.DB_PASSWORD || 'postgres'}@${process.env.DB_HOST || 'localhost'}:${process.env.DB_PORT || '5432'}/${process.env.DB_NAME || 'mtus_db'}`;

let pool: Pool | null = null;
let dbReady = false;

function getPool(): Pool {
  if (!pool) {
    pool = new Pool({
      connectionString: DATABASE_URL,
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });

    pool.on('error', (err) => {
      console.error('[DB] Unexpected pool error:', err.message);
    });
  }
  return pool;
}

// ─── Schema Init ──────────────────────────────────────────────────────────────

export async function initDB(): Promise<boolean> {
  try {
    const client = await getPool().connect();
    try {
      await client.query(`
        CREATE TABLE IF NOT EXISTS positions (
          position_id         TEXT PRIMARY KEY,
          mint                TEXT NOT NULL,
          token_name          TEXT DEFAULT '',
          token_symbol        TEXT DEFAULT '',
          entry_price_sol     DOUBLE PRECISION DEFAULT 0,
          entry_amount_sol    DOUBLE PRECISION DEFAULT 0,
          tokens_received     DOUBLE PRECISION DEFAULT 0,
          entry_tx_signature  TEXT DEFAULT '',
          entry_timestamp_utc TEXT DEFAULT '',
          state               TEXT NOT NULL DEFAULT 'OPEN',
          tp1_price           DOUBLE PRECISION DEFAULT 0,
          tp2_price           DOUBLE PRECISION DEFAULT 0,
          sl_price            DOUBLE PRECISION DEFAULT 0,
          peak_price_sol      DOUBLE PRECISION DEFAULT 0,
          exit_price_sol      DOUBLE PRECISION,
          exit_tx_signature   TEXT,
          realised_pnl_sol    DOUBLE PRECISION,
          qualification_report TEXT,
          created_at          TEXT DEFAULT '',
          updated_at          TEXT DEFAULT ''
        )
      `);

      await client.query(`
        CREATE TABLE IF NOT EXISTS audit_ledger (
          id              SERIAL PRIMARY KEY,
          envelope_id     TEXT DEFAULT '',
          agent_id        TEXT DEFAULT '',
          event_type      TEXT DEFAULT '',
          payload         TEXT DEFAULT '',
          timestamp_utc   TEXT DEFAULT ''
        )
      `);

      // Index for fast open position queries (used on every monitoring tick)
      await client.query(`
        CREATE INDEX IF NOT EXISTS idx_positions_state ON positions(state)
      `);

      dbReady = true;
      console.log('[DB] PostgreSQL initialized successfully');
      return true;
    } finally {
      client.release();
    }
  } catch (e: any) {
    console.error('[DB] PostgreSQL init failed:', e.message);
    return false;
  }
}

// Auto-init on import (unless in test environment)
if (process.env.NODE_ENV !== 'test') {
  initDB().then(() => {
    console.log('[DB] Database ready');
  }).catch((e) => {
    console.error('[DB] Init failed:', e.message);
  });
}

// ─── insertPosition ───────────────────────────────────────────────────────────

export const insertPosition = {
  run: async function (params: any): Promise<void> {
    if (!dbReady) {
      console.log('[DB] insertPosition: DB not ready');
      return;
    }
    try {
      await getPool().query(
        `INSERT INTO positions (
          position_id, mint, token_name, token_symbol, entry_price_sol, entry_amount_sol,
          tokens_received, entry_tx_signature, entry_timestamp_utc, state, tp1_price,
          tp2_price, sl_price, peak_price_sol, created_at, updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        ON CONFLICT (position_id) DO UPDATE SET
          state               = EXCLUDED.state,
          peak_price_sol      = EXCLUDED.peak_price_sol,
          updated_at          = EXCLUDED.updated_at`,
        [
          params.position_id,
          params.mint,
          params.token_name || '',
          params.token_symbol || '',
          params.entry_price_sol || 0,
          params.entry_amount_sol || 0,
          params.tokens_received || 0,
          params.entry_tx_signature || '',
          params.entry_timestamp_utc || '',
          params.state || 'OPEN',
          params.tp1_price || 0,
          params.tp2_price || 0,
          params.sl_price || 0,
          params.peak_price_sol || 0,
          params.created_at || new Date().toISOString(),
          params.updated_at || new Date().toISOString(),
        ]
      );
      console.log('[DB] Position saved:', params.position_id);
    } catch (e: any) {
      console.error('[DB] insertPosition error:', e.message);
    }
  },
};

// ─── updatePosition ───────────────────────────────────────────────────────────

export const updatePosition = {
  run: async function (params: any): Promise<void> {
    if (!dbReady) {
      console.log('[DB] updatePosition: DB not ready');
      return;
    }
    try {
      await getPool().query(
        `UPDATE positions SET
          state               = $1,
          peak_price_sol      = $2,
          exit_price_sol      = $3,
          exit_tx_signature   = $4,
          realised_pnl_sol    = $5,
          updated_at          = $6
        WHERE position_id = $7`,
        [
          params.state || 'OPEN',
          params.peak_price_sol || 0,
          params.exit_price_sol ?? null,
          params.exit_tx_signature ?? null,
          params.realised_pnl_sol ?? null,
          params.updated_at || new Date().toISOString(),
          params.position_id,
        ]
      );
    } catch (e: any) {
      console.error('[DB] updatePosition error:', e.message);
    }
  },
};

// ─── insertAuditLog ───────────────────────────────────────────────────────────

export const insertAuditLog = {
  run: async function (params: any): Promise<void> {
    try {
      await getPool().query(
        `INSERT INTO audit_ledger (envelope_id, agent_id, event_type, payload, timestamp_utc)
         VALUES ($1, $2, $3, $4, $5)`,
        [
          params.envelope_id || '',
          params.agent_id || '',
          params.event_type || '',
          typeof params.payload === 'string'
            ? params.payload
            : JSON.stringify(params.payload || {}),
          params.timestamp_utc || new Date().toISOString(),
        ]
      );
    } catch (e: any) {
      console.error('[DB] insertAuditLog error:', e.message);
    }
  },
};

// ─── getOpenPositions ─────────────────────────────────────────────────────────

export const getOpenPositions = {
  run: async function (): Promise<any[]> {
    if (!dbReady) {
      console.log('[DB] getOpenPositions: DB not ready');
      return [];
    }
    try {
      const result = await getPool().query(
        `SELECT * FROM positions WHERE state = 'OPEN'`
      );
      return result.rows;
    } catch (e: any) {
      console.error('[DB] getOpenPositions error:', e.message);
      return [];
    }
  },
};

// ─── exportAuditLogToJSON ─────────────────────────────────────────────────────

import * as fs from 'fs';
import * as path from 'path';

export async function exportAuditLogToJSON(outputPath?: string): Promise<string | null> {
  try {
    const result = await getPool().query(
      `SELECT * FROM audit_ledger ORDER BY timestamp_utc DESC`
    );
    const records = result.rows.map((row: any) => {
      try { row.payload = JSON.parse(row.payload); } catch {}
      return row;
    });

    const exportData = {
      exported_at: new Date().toISOString(),
      total_records: records.length,
      records,
    };

    const dataDir = path.join(__dirname, '../../data');
    if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

    const exportPath = outputPath || path.join(dataDir, 'audit_export.json');
    fs.writeFileSync(exportPath, JSON.stringify(exportData, null, 2));
    console.log(`[DB] Audit export: ${records.length} records -> ${exportPath}`);
    return exportPath;
  } catch (e: any) {
    console.error('[DB] exportAuditLog error:', e.message);
    return null;
  }
}

// ─── shutdownDB ───────────────────────────────────────────────────────────────

export async function shutdownDB(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
  console.log('[DB] PostgreSQL pool closed');
}

// Daily audit export (non-test environments)
if (process.env.NODE_ENV !== 'test') {
  setInterval(() => {
    const exportPath = path.join(__dirname, '../../data', 'audit_daily.json');
    exportAuditLogToJSON(exportPath).catch(() => {});
  }, 24 * 60 * 60 * 1000);
}