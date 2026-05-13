import { Connection, Keypair, LAMPORTS_PER_SOL, SystemProgram, Transaction, sendAndConfirmTransaction } from "@solana/web3.js";
import Redis from 'ioredis';
import { createRedisClient } from "../shared/redis";
import { createEnvelope } from "../shared/envelope";
import { CHANNEL_SWEEP_COMPLETED, CHANNEL_TRADE_FAILED } from "../shared/channels";
import { loadKeypairFromKeystore } from "../shared/keystore";

const SWEEP_THRESHOLD_SOL = 2.0; // Profit threshold to sweep
const RESERVE_SOL = 0.5; // Amount to keep in Sniper wallet for fees
const POLLING_INTERVAL_MS = 60000; // 1 minute

export class JanusAgent {
  private redis!: Redis;
  private connection: Connection;
  private sniperKeypair: Keypair | null = null;
  private mainKeypair: Keypair | null = null;
  private running: boolean = false;
  private config: any;

  constructor(config: any = {}) {
    this.config = config;
    
    const rpcUrl = process.env.HELIUS_RPC_URL || 'https://api.mainnet-beta.solana.com';
    this.connection = new Connection(rpcUrl, 'confirmed');
    
    console.log("JanusAgent (AGT-07) initialized");
  }

  public async init(redis?: Redis): Promise<void> {
    this.redis = redis || await createRedisClient();
    console.log('[Janus] Initialized');
  }

  public isPaperMode(): boolean {
    const envVar = process.env.MTUS_ENVIRONMENT;
    if (envVar) return envVar.toLowerCase() === 'paper';
    if (this.config?.system?.environment) {
      return this.config.system.environment.toLowerCase() === 'paper';
    }
    return true;
  }

  private static instance: JanusAgent | null = null;

  public static getInstance(config: any = {}): JanusAgent {
    if (!JanusAgent.instance) {
      JanusAgent.instance = new JanusAgent(config);
    }
    return JanusAgent.instance;
  }

  async loadWallets(sniperPass: string, mainPass: string): Promise<void> {
    const sniperPath = process.env.SNIPER_KEYSTORE_PATH || 'keystore/sniper.json';
    const mainPath = process.env.MAIN_KEYSTORE_PATH || 'keystore/main.json';
    
    try {
      this.sniperKeypair = await loadKeypairFromKeystore(sniperPath, sniperPass);
      this.mainKeypair = await loadKeypairFromKeystore(mainPath, mainPass);
      console.log(`[OK] Janus wallets loaded. Sniper: ${this.sniperKeypair.publicKey.toBase58().slice(0,8)}... | Main: ${this.mainKeypair.publicKey.toBase58().slice(0,8)}...`);
    } catch (e: any) {
      throw new Error(`Failed to load wallets: ${e.message}`);
    }
  }

  async run(): Promise<void> {
    if (!this.sniperKeypair || !this.mainKeypair) {
      throw new Error("Wallets not loaded. Call loadWallets() first.");
    }

    this.running = true;
    console.log(`[START] Janus monitoring Sniper balance...`);

    while (this.running) {
      try {
        const balance = await this.connection.getBalance(this.sniperKeypair.publicKey);
        const balanceSol = balance / LAMPORTS_PER_SOL;
        
        console.log(`[MONITOR] Sniper Balance: ${balanceSol.toFixed(4)} SOL | Threshold: ${SWEEP_THRESHOLD_SOL} SOL`);

        if (balanceSol >= SWEEP_THRESHOLD_SOL) {
          await this.sweepProfits(balanceSol);
        }
      } catch (e: any) {
        console.error(`[LOOP ERROR] Janus: ${e.message}`);
      }
      
      if (this.running) {
        await new Promise(r => setTimeout(r, POLLING_INTERVAL_MS));
      }
    }
  }

  private async sweepProfits(currentBalanceSol: number): Promise<void> {
    if (!this.sniperKeypair || !this.mainKeypair) return;

    const amountToSweepSol = currentBalanceSol - RESERVE_SOL;
    if (amountToSweepSol <= 0.05) return; // Don't sweep tiny amounts

    console.log(`[SWEEP] 🧹 Sweeping ${amountToSweepSol.toFixed(4)} SOL to Main wallet...`);

    try {
      const transaction = new Transaction().add(
        SystemProgram.transfer({
          fromPubkey: this.sniperKeypair.publicKey,
          toPubkey: this.mainKeypair.publicKey,
          lamports: Math.floor(amountToSweepSol * LAMPORTS_PER_SOL),
        })
      );

      const signature = await sendAndConfirmTransaction(
        this.connection,
        transaction,
        [this.sniperKeypair]
      );

      console.log(`[OK] Sweep successful! Sig: ${signature}`);

      const envelope = createEnvelope('AGT-07', 'sweep_completed', {
        amount_sol: amountToSweepSol,
        tx_signature: signature,
        timestamp: new Date().toISOString()
      });
      
      await this.redis.publish(CHANNEL_SWEEP_COMPLETED, JSON.stringify(envelope));
    } catch (e: any) {
      console.error(`[ERROR] Sweep failed: ${e.message}`);
      const errorEnvelope = createEnvelope('AGT-07', 'trade_failed', {
        error: `Sweep failed: ${e.message}`,
        type: 'SWEEP_ERROR'
      });
      await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(errorEnvelope));
    }
  }

  async stop(): Promise<void> {
    this.running = false;
    await this.redis.quit();
    console.log("[STOP] Janus agent stopped");
  }

  // Helper for testing
  async checkSniperBalance(): Promise<number> {
    if (!this.sniperKeypair) return 0;
    const balance = await this.connection.getBalance(this.sniperKeypair.publicKey);
    return balance / LAMPORTS_PER_SOL;
  }
}
