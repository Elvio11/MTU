/**
 * Janus Agent Entry Point
 * Run: node dist/agents/janus_start.js
 */

require('dotenv').config();
const { JanusAgent } = require('./janus');

// Validate config at startup (Section 6.1)
try {
  // Use absolute path since PM2 runs from project root
  require('../shared/config_validator.js').validateConfigAtStartup();
} catch(e: any) {
  console.log('[CONFIG] Validation skipped:', e.message);
}

async function main() {
  console.log('='.repeat(50));
  console.log('Janus Agent (AGT-07) - Capital Manager');
  console.log('='.repeat(50));
  
  const agent = new JanusAgent();
  
  try {
    console.log('[OK] Agent created');
    
    // Read passphrases from stdin in production (Section 4.1)
    const { readPassphraseStdin } = require('../shared/passphrase.js');
    let sniperPass: string;
    let mainPass: string;
    
    // Check if running in PM2 (no TTY) or production
    if (process.stdin.isTTY && !process.env.PM2_HOME) {
      console.log('Janus Agent - Passphrase Entry');
      sniperPass = await readPassphraseStdin('Enter Sniper wallet passphrase: ');
      mainPass = await readPassphraseStdin('Enter Main wallet passphrase: ');
    } else if (process.env.SNIPER_PASSPHRASE && process.env.MAIN_PASSPHRASE) {
      console.log('[WARN] Using env var passphrases - NOT RECOMMENDED for production!');
      sniperPass = process.env.SNIPER_PASSPHRASE;
      mainPass = process.env.MAIN_PASSPHRASE;
    } else {
      console.log('[ERROR] No passphrases provided. Set SNIPER_PASSPHRASE and MAIN_PASSPHRASE or run with TTY for stdin input.');
      process.exit(1);
    }
    
    try {
      await agent.loadWallets(sniperPass, mainPass);
      // Zero passphrase variables
      sniperPass = '';
      mainPass = '';
    } catch (e: any) {
      console.log('[ERROR] Could not load wallets:', e?.message || e);
      process.exit(1);
    }
    
    await agent.run();
    console.log('\n✅ Janus agent is running...');
    console.log('   Managing capital allocation...\n');
    
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

main();