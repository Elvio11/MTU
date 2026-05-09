#!/usr/bin/env node
/**
 * Publish a test trade_approved message to trigger Ares trading
 */

const { createEnvelope } = require('../dist/shared/envelope.js');
const MockRedis = require('../dist/shared/mock_redis.js').default;

async function main() {
  const redis = new MockRedis();
  await redis.connect();
  
  const envelope = createEnvelope(
    'AGT-01',
    'trade_approved',
    {
      token: {
        mint: 'JUPyiwrYJFJ3nKSHp4fVGFuckq6S1VQk1k5u3yG1Zhc',
        name: 'JUP',
        symbol: 'JUP'
      }
    },
    'test-trade-001'
  );
  
  console.log('Publishing trade_approved event...');
  await redis.publish('trade_approved', JSON.stringify(envelope));
  console.log('Event published!');
  
  setTimeout(() => redis.quit(), 1000);
}

main().catch(console.error);