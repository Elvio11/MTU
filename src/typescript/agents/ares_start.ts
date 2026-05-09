/**
 * Ares Agent Entry Point
 * Run: node dist/agents/ares_start.js
 */

require('dotenv').config();
const { AresAgent } = require('./ares');

// Validate config at startup (Section 6.1)
try {
  // Use absolute path since PM2 runs from project root
  require('../shared/config_validator.js').validateConfigAtStartup();
} catch(e: any) {
  console.log('[CONFIG] Validation skipped:', e.message);
}

async function aresMain() {
  console.log('='.repeat(50));
  console.log('Ares Agent (AGT-05) - Trade Executor');
  console.log('='.repeat(50));
  
  const agent = new AresAgent();
  
  try {
    await agent.init();
    console.log('[OK] Agent initialized');
    
    // Load wallet - passphrase from stdin for security (Section 4.1)
    const { readPassphraseStdin } = require('../shared/passphrase.js');
    let passphrase: string;
    
    // Check if running in PM2 (no TTY) or production
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
      await agent.loadSniperWallet(passphrase);
      // Zero the passphrase variable
      passphrase = '';
    } catch (e: any) {
      console.log('[ERROR] Could not load wallet:', e?.message || e);
      process.exit(1);
    }
    
    // Start the agent
    await agent.run();
    console.log('\n✅ Ares agent is running...');
    console.log('   Waiting for trade_approved events...\n');
    
    // Keep running
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

aresMain();