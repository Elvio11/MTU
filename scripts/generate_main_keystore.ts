/**
 * Generate main keystore
 */
const { createKeystore, loadKeypairFromKeystore } = require('../dist/shared/keystore');
const { Keypair } = require('@solana/web3.js');

async function main() {
  const keypair = Keypair.generate();
  console.log('Generated main wallet:', keypair.publicKey.toBase58());
  
  const passphrase = 'change_this_password';
  await createKeystore(keypair.secretKey, passphrase, '../keystores/main.keystore');
  console.log('Created: ../keystores/main.keystore');
  
  const loaded = await loadKeypairFromKeystore('../keystores/main.keystore', passphrase);
  console.log('Loaded:', loaded.publicKey.toBase58());
}

main().catch(console.error);