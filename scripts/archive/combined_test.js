/**
 * Combined test: Start agent and trigger trade in same process
 */

const { AresAgent } = require('../dist/agents/ares');
const { createEnvelope } = require('../dist/shared/envelope');

async function main() {
  console.log('='.repeat(60));
  console.log('MTUS Paper Trading Test - Combined Process');
  console.log('='.repeat(60));
  
  const agent = new AresAgent();
  
  // Initialize (uses mock Redis)
  await agent.init();
  console.log('[OK] Agent initialized');
  
  // Start the agent (subscribes to trade_approved)
  await agent.run();
  console.log('[OK] Agent subscribed to trade_approved\n');
  
  // Wait a bit
  await new Promise(r => setTimeout(r, 1000));
  
  // Create and publish a trade_approved event
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
  
  console.log('Publishing trade_approved event...\n');
  await agent.redis.publish('trade_approved', JSON.stringify(envelope));
  
  // Wait for processing
  await new Promise(r => setTimeout(r, 3000));
  
  console.log('\n✅ Test complete');
  await agent.stop();
  process.exit(0);
}

main().catch(e => {
  console.error('Error:', e);
  process.exit(1);
});