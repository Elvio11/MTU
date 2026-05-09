/**
 * Sentinel Agent Entry Point
 * Run: node dist/agents/sentinel_start.js
 */

const { SentinelAgent } = require('./sentinel');

async function sentinelMain() {
  console.log('='.repeat(50));
  console.log('Sentinel Agent (AGT-06) - Position Monitor');
  console.log('='.repeat(50));
  
  const agent = new SentinelAgent();
  
  try {
    console.log('[OK] Agent initialized');
    
    // Load wallet - passphrase from stdin for security
    const { readPassphraseStdin } = require('../shared/passphrase.js');
    let passphrase: string;
    
    if (process.stdin.isTTY && !process.env.PM2_HOME) {
      passphrase = await readPassphraseStdin('Enter Sniper passphrase: ');
    } else if (process.env.SNIPER_PASSPHRASE && process.env.SNIPER_PASSPHRASE !== 'test123') {
      console.log('[WARN] Using env var passphrase - NOT RECOMMENDED for production!');
      passphrase = process.env.SNIPER_PASSPHRASE;
    } else {
      console.log('[ERROR] No passphrase provided. Set SNIPER_PASSPHRASE or run with TTY for stdin input.');
      process.exit(1);
    }
    
    try {
      await agent.loadKeypair(passphrase);
      passphrase = '';
    } catch (e: any) {
      console.log('[ERROR] Could not load wallet:', e?.message || e);
      process.exit(1);
    }
    
    await agent.run();
    console.log('\n✅ Sentinel agent is running...');
    console.log('   Monitoring positions...\n');
    
    process.on('SIGINT', async () => {
      console.log('\nShutting down...');
      await agent.stop();
      process.exit(0);
    });
    
  } catch (e: any) {
    console.error('[ERROR] Failed to start agent:', e?.message || e);
    process.exit(1);
  }
}

sentinelMain();