import { Connection, PublicKey } from '@solana/web3.js';
import * as dotenv from 'dotenv';
import * as path from 'path';

dotenv.config();

async function checkBalances() {
  const HELIUS_RPC_URL = process.env.HELIUS_RPC_URL || 'https://mainnet.helius-rpc.com/?api-key=' + process.env.HELIUS_KEY;
  const connection = new Connection(HELIUS_RPC_URL);

  const sniperWallet = new PublicKey('ESHH2KcsMWSKoA6ypBGfbpP8Mre3k1QVw4jkypn8A1xc');
  const mainWallet = new PublicKey('8K7sR6k1vP9M9e1vP9M9e1vP9M9e1vP9M9e1vP9M9e1v'); // Placeholder

  try {
    const sniperBalance = await connection.getBalance(sniperWallet);
    console.log(`Sniper Wallet (${sniperWallet.toBase58()}): ${sniperBalance / 1e9} SOL`);
    
    // Check if enough for 10 trades
    const minNeeded = 0.05; // 0.005 * 10
    if (sniperBalance / 1e9 < minNeeded) {
        console.warn(`[WARNING] Sniper balance low! Need at least ${minNeeded} SOL for 10 trades.`);
    } else {
        console.log(`[OK] Sniper balance sufficient for at least ${Math.floor(sniperBalance / 1e9 / 0.005)} trades.`);
    }
  } catch (e: any) {
    console.error(`Failed to fetch sniper balance: ${e.message}`);
  }
}

checkBalances();
