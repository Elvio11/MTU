/**
 * Regenerate both sniper and main wallet keystores with NEW passphrases
 * Run: npx ts-node scripts/regenerate_keystores.ts
 */

const { Keypair } = require('@solana/web3.js');
const { createKeystore, loadKeypairFromKeystore } = require('../dist/shared/keystore');

const SNIPER_PASSPHRASE = 'MTUS_2025_Sniper#X9kZ';
const MAIN_PASSPHRASE = 'MTUS_2025_Main#Y8pQ';

async function regenerate() {
  console.log('=========================================');
  console.log('MTUS Wallet Regeneration');
  console.log('=========================================');
  console.log('');
  console.log('WARNING: This will generate NEW wallet addresses!');
  console.log('');
  
  // Generate new Sniper wallet
  console.log('[1/2] Generating NEW Sniper wallet...');
  const sniperKeypair = Keypair.generate();
  console.log('  Public Key:', sniperKeypair.publicKey.toBase58());
  
  await createKeystore(
    sniperKeypair.secretKey,
    SNIPER_PASSPHRASE,
    './keystores/sniper.keystore'
  );
  console.log('  ✅ Keystore saved: keystores/sniper.keystore');
  console.log('  🔑 Passphrase:', SNIPER_PASSPHRASE);
  console.log('');

  // Generate new Main wallet
  console.log('[2/2] Generating NEW Main wallet...');
  const mainKeypair = Keypair.generate();
  console.log('  Public Key:', mainKeypair.publicKey.toBase58());
  
  await createKeystore(
    mainKeypair.secretKey,
    MAIN_PASSPHRASE,
    './keystores/main.keystore'
  );
  console.log('  ✅ Keystore saved: keystores/main.keystore');
  console.log('  🔑 Passphrase:', MAIN_PASSPHRASE);
  console.log('');

  // Verify
  console.log('Verifying keystores...');
  const loadedSniper = await loadKeypairFromKeystore('./keystores/sniper.keystore', SNIPER_PASSPHRASE);
  const loadedMain = await loadKeypairFromKeystore('./keystores/main.keystore', MAIN_PASSPHRASE);
  
  console.log('');
  console.log('=========================================');
  console.log('✅ Wallets Regenerated Successfully!');
  console.log('=========================================');
  console.log('');
  console.log('SNIPER WALLET (for trading):');
  console.log('  Address:', loadedSniper.publicKey.toBase58());
  console.log('  Fund with: 0.009 SOL');
  console.log('');
  console.log('MAIN WALLET (vault):');
  console.log('  Address:', loadedMain.publicKey.toBase58());
  console.log('  Fund with: 0.001 SOL');
  console.log('');
  console.log('⚠️  IMPORTANT: Fund these wallets BEFORE running the bot!');
  console.log('');
}

regenerate().catch(console.error);