#!/usr/bin/env node
/**
 * Quick Start Script - Run Ares Agent and test trading
 */

const { AresAgent } = require('./dist/agents/ares');
const { createEnvelope } = require('./dist/shared/envelope');

async function main() {
  console.log('='.repeat(50));
  console.log('MTUS - Starting Ares Agent');
  console.log('='.repeat(50));
  
  const agent = new AresAgent();
  
  try {
    await agent.init();
    console.log('[OK] Agent initialized');
    
    await agent.run();
    console.log('[OK] Subscribed to trade_approved');
    
    // Wait a moment
    await new Promise(r => setTimeout(r, 1000));
    
    // Publish test trade
    console.log('\nPublishing test trade_approved event...');
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
    
    await agent.redis.publish('trade_approved', JSON.stringify(envelope));
    console.log('[OK] Event published');
    
    // Wait for processing
    await new Promise(r => setTimeout(r, 3000));
    
    console.log('\n✅ Agent test complete!');
    
  } catch (e) {
    console.error('Error:', e.message);
  } finally {
    await agent.stop();
  }
}

main();