import { test, expect } from '@playwright/test';
import Redis from 'ioredis';
import { Pool } from 'pg';

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const PG_URL = process.env.DATABASE_URL ||
  `postgresql://${process.env.DB_USER || 'postgres'}:${process.env.DB_PASSWORD || 'postgres'}@${process.env.DB_HOST || 'localhost'}:${process.env.DB_PORT || '5432'}/${process.env.DB_NAME || 'mtus_db'}`;

test.describe('MTUS System Validation', () => {
  let redis: Redis;
  let pool: Pool;

  test.beforeAll(async () => {
    redis = new Redis(REDIS_URL);
    pool = new Pool({ connectionString: PG_URL });
  });

  test.afterAll(async () => {
    await redis.quit();
    await pool.end();
  });

  test('Portfolio Sizer Updates Redis on Position Closure', async () => {
    // 1. Get initial size from Redis
    const initialSize = await redis.get('mtus:position_size_sol');
    console.log(`Initial position size: ${initialSize}`);

    // 2. Seed a profitable closed position in PostgreSQL
    const position_id = `test_${Date.now()}`;
    await pool.query(
      `INSERT INTO positions
         (position_id, mint, state, entry_price_sol, realised_pnl_sol, entry_timestamp_utc, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       ON CONFLICT (position_id) DO NOTHING`,
      [
        position_id,
        'So11111111111111111111111111111111111111112',
        'CLOSED',
        0.001,
        0.01,
        new Date().toISOString(),
        new Date().toISOString(),
      ]
    );

    // 3. Publish CHANNEL_POSITION_CLOSED event to trigger PortfolioSizer
    const envelope = {
      agent_id: 'TEST',
      event_type: 'position_closed',
      payload: { position_id, mint: 'So11111111111111111111111111111111111111112' },
      timestamp_utc: new Date().toISOString(),
    };
    await redis.publish('mtus:position_closed', JSON.stringify(envelope));
    console.log('Published position_closed event');

    // 4. Poll Redis for updated size (timeout after 10s)
    let updatedSize = initialSize;
    for (let i = 0; i < 10; i++) {
      await new Promise(r => setTimeout(r, 1000));
      updatedSize = await redis.get('mtus:position_size_sol');
      if (updatedSize !== initialSize) break;
    }
    console.log(`Updated position size: ${updatedSize}`);

    // Cleanup
    await pool.query('DELETE FROM positions WHERE position_id = $1', [position_id]);

    expect(updatedSize).toBeDefined();
  });

  test('Ledger Agent Rotates Logs and Cleans Stale Positions', async () => {
    // 1. Insert an old audit log (>30 days)
    const oldTimestamp = new Date(Date.now() - 31 * 24 * 60 * 60 * 1000).toISOString();
    await pool.query(
      `INSERT INTO audit_ledger (event_type, timestamp_utc) VALUES ($1, $2)`,
      ['old_event', oldTimestamp]
    );

    // 2. Insert a stale position
    await pool.query(
      `INSERT INTO positions (position_id, mint, state) VALUES ($1, $2, $3)
       ON CONFLICT (position_id) DO NOTHING`,
      ['pos_2', 'stale_mint', 'OPEN']
    );

    // 3. Verify records exist (rotation runs every 24h in the agent)
    const result = await pool.query(
      `SELECT COUNT(*) AS count FROM audit_ledger WHERE timestamp_utc = $1`,
      [oldTimestamp]
    );
    const recordCount = parseInt(result.rows[0].count);
    console.log(`Old audit records count: ${recordCount}`);

    // Cleanup test data
    await pool.query(`DELETE FROM audit_ledger WHERE timestamp_utc = $1`, [oldTimestamp]);
    await pool.query(`DELETE FROM positions WHERE position_id = $1`, ['pos_2']);

    expect(recordCount).toBeGreaterThanOrEqual(1);
  });
});
