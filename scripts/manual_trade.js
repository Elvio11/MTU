#!/usr/bin/env node
/**
 * Manual Trade Trigger - Simulates token qualification and trade execution
 * Use this to test the full system flow without waiting for PumpPortal
 */

require('dotenv').config();
const { createEnvelope } = require('../dist/shared/envelope');
const Redis = require('ioredis');

const REDIS_URL = process.env.REDIS_URL || 'redis://127.0.0.1:6379';

async function main() {
  console.log('='.repeat(60));
  console.log('MTUS Manual Trade Trigger');
  console.log('='.repeat(60));
  console.log('');

  const redis = new Redis(REDIS_URL, {
    connectTimeout: 5000,
    retryStrategy: (times) => Math.min(times * 100, 3000)
  });

  try {
    await redis.ping();
    console.log('✅ Redis connected\n');
  } catch (e) {
    console.log('❌ Redis connection failed:', e.message);
    process.exit(1);
  }

  // Use a test token mint (this is a real token - $WIF on Solana)
  const testMint = '85VBFoZCqCYpfS2z1FLn1g3pV5xL6Z5xPqY8vZ5xL6Z5'; // Example
  
  console.log('📤 Publishing trade_approved event directly...');
  console.log('   This bypasses NOFX and Anansi qualification!');
  console.log('   Use this to test the execution flow only.\n');

  const correlationId = `manual-${Date.now()}`;
  
  const tradeApproved = createEnvelope(
    'AGT-03',  // From Anansi
    'trade_approved',
    {
      token: {
        mint: testMint,
        name: 'Test Token',
        symbol: 'TEST',
        marketCapSol: 50
      },
      position_size_sol: 0.0001,
      entry_price_sol: 0.00001,
      gates_passed: ['G1', 'G2', 'G7', 'G10']
    },
    correlationId
  );

  console.log('Publishing to trade_approved channel...');
  await redis.publish('trade_approved', JSON.stringify(tradeApproved));
  
  console.log('\n✅ Event published!');
  console.log('   Correlation ID:', correlationId);
  console.log('');
  console.log('Watch ares-executor logs:');
  console.log('   pm2 logs ares-executor');
  console.log('');
  console.log('Or check Redis for position:');
  console.log(`   redis-cli GET mtus:position:${correlationId}`);

  await redis.quit();
  console.log('\n✅ Done');
}

main().catch(e => {
  console.error('Error:', e);
  process.exit(1);
});