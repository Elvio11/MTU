/**
 * Generate keystores using TypeScript/Node
 */

const { createKeystore, loadKeypairFromKeystore } = require('../dist/shared/keystore');
const { Keypair } = require('@solana/web3.js');

async function main() {
  // Generate new keypair
  const keypair = Keypair.generate();
  console.log('Generated public key:', keypair.publicKey.toBase58());
  
  const passphrase = "change_this_password";
  
  // Create keystore
  await createKeystore(
    keypair.secretKey,
    passphrase,
    '../keystores/sniper.keystore'
  );
  console.log('Created: ../keystores/sniper.keystore');
  
  // Test loading
  const loaded = await loadKeypairFromKeystore('../keystores/sniper.keystore', passphrase);
  console.log('Loaded public key:', loaded.publicKey.toBase58());
}

main().catch(console.error);