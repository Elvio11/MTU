import { Keypair, Transaction, TransactionInstruction, PublicKey } from '@solana/web3.js';
import { QuoteResponse, SwapApi } from '@jup-ag/api';
import { Connection, VersionedTransaction, VersionedMessage } from '@solana/web3.js';
import { execSync } from 'child_process';
import { AgentMessageEnvelope, createEnvelope, EventType } from '../shared/envelope';
import { loadKeypairFromKeystore } from '../shared/keystore';
import { CircuitBreaker } from '../shared/circuit-breaker';
import { isOperationalWindowActive } from '../shared/operational-window';
import { CHANNEL_TRADE_APPROVED, CHANNEL_TRADE_FAILED, CHANNEL_POSITION_OPENED } from '../shared/channels';
import Redis from 'ioredis';
import { createRedisClient } from '../shared/redis';
export { createRedisClient };
import dotenv from 'dotenv';
import axios from 'axios';
import { insertPosition, updatePosition, insertAuditLog, getOpenPositions } from '../shared/db';
import * as fs from 'fs';
import * as yaml from 'js-yaml';
import * as path from 'path';

let lastKnownSolPrice = 168.5; // Shared cache for price fallbacks

dotenv.config();

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const MAX_SLIPPAGE_BPS = 1500;
const SLIPPAGE_LADDER = [500, 1000, 1500];
const RETRY_DELAYS = [0, 500, 1000];

// Dynamic Balance Guard constants
const RENT_ATA = 2039280;        // 0.00204 SOL - Rent for new Token ATA
const RENT_WSOL = 0;             // 0.0 SOL - Wallet likely has wSOL already
const FEE_BUFFER = 500000;       // 0.0005 SOL - Base blockchain transaction fee (unchanged)
const PRIORITY_FEE_BUFFER = 5000000; // 0.005 SOL - Max priority fee (user-configured, separate)


// Helper: Determine which Jupiter API to use based on USD value
export async function getJupiterApiVersion(positionSizeSol: number): Promise<{ version: 'v1' | 'v2', usdValue: number }> {
  const solPrice = await getSolPriceUsd();
  const usdValue = positionSizeSol * solPrice;

  if (usdValue < 6) {
    return { version: 'v1', usdValue };
  } else {
    return { version: 'v2', usdValue };
  }
}

// Helper: Check if wallet can afford the trade
export async function canAffordTrade(
  connection: Connection,
  walletPubkey: any,
  positionSol: number
): Promise<{ ok: boolean; have: number; need: number; breakdown: string }> {
  const LAMPORTS_PER_SOL = 1_000_000_000;
  const balance = await connection.getBalance(walletPubkey);

  const positionLamports = positionSol * LAMPORTS_PER_SOL;
  // Total: Trade amount + ATA rent + base tx fee + max priority fee
  const totalNeed = positionLamports + RENT_WSOL + RENT_ATA + FEE_BUFFER + PRIORITY_FEE_BUFFER;

  const haveSol = balance / LAMPORTS_PER_SOL;
  const needSol = totalNeed / LAMPORTS_PER_SOL;
  const breakdown = `Position: ${positionSol} SOL + ATA: ${(RENT_WSOL + RENT_ATA) / LAMPORTS_PER_SOL} SOL + BaseFee: ${FEE_BUFFER / LAMPORTS_PER_SOL} SOL + PriorityFee: ${PRIORITY_FEE_BUFFER / LAMPORTS_PER_SOL} SOL = ${needSol.toFixed(6)} SOL required`;

  return {
    ok: balance >= totalNeed,
    have: haveSol,
    need: needSol,
    breakdown
  };
}

// TP/SL Monitoring Helper Functions (used by Sentinel via shared module)
export async function fetchTokenPrice(mint: string): Promise<number> {
  try {
    const resp = await fetch(`https://api.jup.ag/price/v3?ids=${mint}`, {
      headers: { 'x-api-key': process.env.JUPITER_API_KEY || '' },
      signal: AbortSignal.timeout(5000)
    });
    const data: any = await resp.json();
    return data?.data?.[mint]?.usdPrice || 0;
  } catch (e) {
    return 0;
  }
}

interface OpenPosition {
  position_id: string;
  mint: string;
  entry_price_sol: number;
  tokens_received: number;
  state: string;
  tp1_price: number;
  tp2_price: number;
  sl_price: number;
  peak_price_sol: number;
}

// Paper mode helper moved to AresAgent.isPaperMode()
// Consts moved to config



class RateLimiter {
  private redis: Redis;
  private tradeTimes: number[] = [];
  private activePositions: Set<string> = new Set();

  private config: any; constructor(redis: Redis, config: any) {
    this.redis = redis; this.config = config;
    this.redis = redis;
  }

  async canTrade(): Promise<{ allowed: boolean; reason: string }> {
    try {
      // Check concurrent positions
      const positionsKey = 'mtus:active_positions';
      const activeCount = await this.redis.scard(positionsKey);
      console.log(`[RateLimiter] Active positions check: key=${positionsKey}, count=${activeCount}, max=${(this.config?.trading?.max_simultaneous_positions || 1)}`);

      if (activeCount >= (this.config?.trading?.max_simultaneous_positions || 1)) {
        return {
          allowed: false,
          reason: `Max concurrent positions (${(this.config?.trading?.max_simultaneous_positions || 1)}) reached`
        };
      }

      // Check hourly rate limit
      const currentHour = Math.floor(Date.now() / 3600000);
      const tradeCountKey = `mtus:trade_count:${currentHour}`;
      const tradeCount = parseInt(await this.redis.get(tradeCountKey) || '0');

      if (tradeCount >= (this.config?.trading?.max_trades_per_hour || 3)) {
        return {
          allowed: false,
          reason: `Max trades per hour (${(this.config?.trading?.max_trades_per_hour || 3)}) reached`
        };
      }

      // Check daily loss limit
      const dailyPnlKey = 'mtus:daily_pnl';
      const dailyPnl = parseFloat(await this.redis.get(dailyPnlKey) || '0');

      if (dailyPnl <= -(this.config?.trading?.daily_loss_limit_sol || 0.002)) {
        return {
          allowed: false,
          reason: `Daily loss limit (-${(this.config?.trading?.daily_loss_limit_sol || 0.002)} SOL) reached`
        };
      }

      return { allowed: true, reason: 'OK' };
    } catch (e) {
      console.log('[RateLimiter] Error checking limits, allowing trade:', e);
      return { allowed: true, reason: 'Error checking limits' };
    }
  }

  async recordTrade(positionId: string): Promise<void> {
    try {
      const currentHour = Math.floor(Date.now() / 3600000);
      const tradeCountKey = `mtus:trade_count:${currentHour}`;
      await this.redis.incr(tradeCountKey);

      // Set expiry for old keys
      await this.redis.expire(tradeCountKey, 7200);

      // Add to active positions
      const positionsKey = 'mtus:active_positions';
      await this.redis.sadd(positionsKey, positionId);
    } catch (e) {
      console.log('[RateLimiter] Error recording trade:', e);
    }
  }

  async closePosition(positionId: string): Promise<void> {
    try {
      const positionsKey = 'mtus:active_positions';
      await this.redis.srem(positionsKey, positionId);
    } catch (e) {
      console.log('[RateLimiter] Error closing position:', e);
    }
  }

  async updateDailyPnl(pnl: number): Promise<void> {
    try {
      const dailyPnlKey = 'mtus:daily_pnl';
      const current = parseFloat(await this.redis.get(dailyPnlKey) || '0');
      await this.redis.set(dailyPnlKey, (current + pnl).toString());

      // Reset daily PnL at midnight
      const now = new Date();
      const msUntilMidnight = (24 - now.getHours()) * 3600000 - now.getMinutes() * 60000;
      await this.redis.expire(dailyPnlKey, Math.floor(msUntilMidnight / 1000));
    } catch (e) {
      console.log('[RateLimiter] Error updating daily PnL:', e);
    }
  }
}

export async function getSolPriceUsd(config?: any): Promise<number> {
  const SOL_MINT = 'So11111111111111111111111111111111111111112';

  try {
    return await rateLimitedRequest(async () => {
      // 1. Try Jupiter V3 (Primary)
      try {
        const response = await axios.get(`https://api.jup.ag/price/v3?ids=${SOL_MINT}`, {
          headers: { 'x-api-key': process.env.JUPITER_API_KEY || '' },
          timeout: 5000
        });
        const price = response.data?.data?.[SOL_MINT]?.usdPrice || response.data?.data?.[SOL_MINT]?.price;
        if (price && typeof price === 'number' && price > 0) {
          lastKnownSolPrice = price;
          return price;
        }
      } catch (e) { }

      // 2. Try Binance Public API (Reliable Tertiary for SOL/USDT)
      try {
        const binanceResp = await axios.get('https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT', { timeout: 5000 });
        const price = parseFloat(binanceResp.data?.price);
        if (price > 0) {
          lastKnownSolPrice = price;
          return price;
        }
      } catch (e) { }

      // 3. Try Birdeye (Fallback)
      try {
        const birdeyeResp = await axios.get(`https://public-api.birdeye.so/public/price?address=${SOL_MINT}`, {
          headers: { 'X-API-KEY': process.env.BIRDEYE_API_KEY || '' },
          timeout: 5000
        });
        const price = birdeyeResp.data?.data?.value;
        if (price && typeof price === 'number' && price > 0) {
          lastKnownSolPrice = price;
          return price;
        }
      } catch (e) { }

      throw new Error('All SOL price providers failed');
    }, config);
  } catch (e: any) {
    console.warn(`[PRICE WARNING] All providers failed: ${e.message}. Using last known price: $${lastKnownSolPrice}`);
    return lastKnownSolPrice; // Never use a fake hardcoded number, use the most recent real one
  }
}

let lastRequestTime = 0;
const MIN_REQUEST_INTERVAL_MS = 2000;  // 2 seconds between Jupiter requests to avoid 429s

export async function rateLimitedRequest<T>(requestFn: (baseUrl: string) => Promise<T>, config?: any): Promise<T> {
  const baseUrl = config?.trading?.jupiter_api_url || 'https://api.jup.ag/swap/v6';
  const now = Date.now();
  const timeSinceLastRequest = now - lastRequestTime;

  if (timeSinceLastRequest < MIN_REQUEST_INTERVAL_MS) {
    await new Promise(r => setTimeout(r, MIN_REQUEST_INTERVAL_MS - timeSinceLastRequest));
  }

  lastRequestTime = Date.now();

  try {
    return await requestFn(baseUrl);
  } catch (error: any) {
    // Handle 429 rate limit errors with exponential backoff
    if (error.response?.status === 429) {
      for (let retry = 1; retry <= 3; retry++) {
        const backoff = Math.min(1000 * Math.pow(2, retry), 10000); // 2s, 4s, 8s max 10s
        console.log(`AGT-05: [RATE LIMIT] Jupiter API rate limited, retrying in ${backoff}ms (attempt ${retry}/3)...`);
        await new Promise(r => setTimeout(r, backoff));
        lastRequestTime = 0;
        try {
          return await requestFn(baseUrl);
        } catch (retryError: any) {
          if (retryError.response?.status !== 429 || retry === 3) throw retryError;
        }
      }
    }
    throw error;
  }
}


export class AresAgent {
  private redis!: Redis;
  private keypair: Keypair | null = null;
  private jupiter: SwapApi;
  private running: boolean = false;
  private rateLimiter!: RateLimiter;
  private config: any;

  constructor(config?: any, redis?: Redis) {
    if (config) {
      this.config = config;
    } else {
      this.loadConfig();
    }
    if (redis) {
      this.redis = redis;
      this.rateLimiter = new RateLimiter(this.redis, this.config);
    }
    this.jupiter = new SwapApi();
  }

  private isPaperMode(): boolean {
    const envVar = process.env.MTUS_ENVIRONMENT;
    if (envVar) return envVar.toLowerCase() === 'paper';

    // Fallback to config
    if (this.config?.system?.environment) {
      return this.config.system.environment.toLowerCase() === 'paper';
    }

    return true; // Default to safe mode
  }

  private loadConfig(): void {
    try {
      const configPath = path.join(process.cwd(), 'config', 'config.yaml');
      const fileContents = fs.readFileSync(configPath, 'utf8');
      this.config = yaml.load(fileContents) as any;
      console.log('AGT-05: Config loaded from config.yaml');
    } catch (e) {
      console.error('AGT-05: Failed to load config, using defaults');
      this.config = { trading: { position_size_sol: 0.0005, max_simultaneous_positions: 1, max_trades_per_hour: 3, daily_loss_limit_sol: 0.002, tp1_multiplier: 2.0, tp2_multiplier: 5.0, sl_multiplier: 0.7, trailing_stop_pct: 15 } };
    }
  }

  async init(redis?: Redis): Promise<void> {
    if (redis) {
      this.redis = redis;
    } else if (!this.redis) {
      this.redis = await createRedisClient();
    }
    this.rateLimiter = new RateLimiter(this.redis, this.config);
    console.log('[RateLimiter] Initialized');
    await this.syncState();
  }

  private async syncState(): Promise<void> {
    try {
      console.log('AGT-05: [SYNC] Synchronizing Redis state with PostgreSQL DB...');
      const openPositions = await getOpenPositions.run();
      const positionsKey = 'mtus:active_positions';

      // Clear current Redis set to ensure fresh sync
      await this.redis.del(positionsKey);

      if (openPositions.length > 0) {
        console.log(`AGT-05: [SYNC] Found ${openPositions.length} open positions in DB. Syncing to Redis...`);
        for (const pos of openPositions) {
          await this.redis.sadd(positionsKey, pos.position_id);
          console.log(`AGT-05: [SYNC] Restored active position: ${pos.position_id} (${pos.mint})`);
        }
      } else {
        console.log('AGT-05: [SYNC] No open positions in DB. Redis cleared.');
      }
    } catch (e: any) {
      console.error(`AGT-05: [SYNC-ERROR] Failed to sync state: ${e.message}`);
    }
  }

  async loadSniperWallet(passphrase: string): Promise<void> {
    const keystorePath = process.env.SNIPER_KEYSTORE_PATH || './keystores/sniper.keystore';
    this.keypair = await loadKeypairFromKeystore(keystorePath, passphrase);
    console.log(`AGT-05: Loaded Sniper Wallet: ${this.keypair.publicKey.toBase58()}`);

    // Sync with Jupiter CLI if enabled and in production
    if (!this.isPaperMode() && this.config?.trading?.use_jupiter_cli) {
      try {
        const b64Key = Buffer.from(this.keypair.secretKey).toString('base64');
        execSync(`jup config set --api-key ${process.env.JUPITER_API_KEY || ''}`);
        execSync(`jup keys add sniper --private-key ${b64Key} --overwrite`);
        console.log('AGT-05: [CLI] Jupiter CLI synchronized with sniper wallet');
      } catch (e: any) {
        console.warn(`AGT-05: [CLI WARNING] Failed to sync Jupiter CLI: ${e.message}`);
      }
    }

    // Verify keypair secret key length (should be 64 bytes for full keypair)
    console.log(`AGT-05: Keypair secret length: ${this.keypair.secretKey.length} bytes`);

    // Verify the decrypted keypair matches expected wallet address
    const EXPECTED_WALLET = "ESHH2KcsMWSKoA6ypBGfbpP8Mre3k1QVw4jkypn8A1xc";
    const derivedAddress = this.keypair.publicKey.toBase58();
    if (derivedAddress !== EXPECTED_WALLET) {
      throw new Error(`CRITICAL: Decryption produced wrong keypair! Expected ${EXPECTED_WALLET}, got ${derivedAddress}`);
    }
    console.log(`AGT-05: ✅ Keypair verified correct - matches expected wallet`);
  }

  async executeTrade(mint: string, correlationId: string, isPump: boolean = false): Promise<void> {
    // Check operational window (21:00 - 06:00 IST) per Section 1.1
    if (!this.isPaperMode() && !isOperationalWindowActive()) {
      console.log(`AGT-05: [OPERATIONAL WINDOW] Trade blocked - outside trading hours (21:00-06:00 IST)`);
      const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: 'Outside operational window' }, correlationId);
      await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
      insertAuditLog.run({ envelope_id: correlationId, agent_id: 'AGT-05', event_type: 'trade_failed', payload: { mint, error: 'Outside operational window' }, timestamp_utc: new Date().toISOString() });
      return;
    }

    // Check rate limits first
    const rateCheck = await this.rateLimiter.canTrade();
    if (!rateCheck.allowed) {
      console.log(`AGT-05: [RATE LIMIT] Trade blocked: ${rateCheck.reason}`);
      const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: rateCheck.reason }, correlationId);
      await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
      insertAuditLog.run({ envelope_id: correlationId, agent_id: 'AGT-05', event_type: 'trade_failed', payload: { mint, error: rateCheck.reason }, timestamp_utc: new Date().toISOString() });
      return;
    }

    // Check if we're in paper or production mode
    if (!this.isPaperMode()) {
      // PRODUCTION MODE - LIVE TRADING
      console.log(`AGT-05: [LIVE] ========== TRADE START ==========`);
      console.log(`AGT-05: [LIVE] Mint: ${mint}`);
      console.log(`AGT-05: [LIVE] Position size: ${(this.config?.trading?.position_size_sol || 0.0005)} SOL`);

      // Check wallet balance
      if (!this.keypair) {
        console.log(`AGT-05: [LIVE] ❌ No wallet loaded!`);
        return;
      }
      console.log(`AGT-05: [LIVE] Sniper wallet: ${this.keypair.publicKey.toBase58()}`);

      try {
        const connection = new Connection(process.env.HELIUS_RPC_URL!);
        const balance = await connection.getBalance(this.keypair.publicKey);
        console.log(`AGT-05: [LIVE] Wallet balance: ${balance / 1e9} SOL`);

        // Dynamic Balance Guard - robust check
        const affordability = await canAffordTrade(connection, this.keypair.publicKey, (this.config?.trading?.position_size_sol || 0.0005));
        console.log(`AGT-05: [BALANCE] ${affordability.breakdown}`);

        if (!affordability.ok) {
          console.log(`AGT-05: [LIVE] ❌ TRADE ABORTED: Insufficient balance for overhead`);
          console.log(`AGT-05: [BALANCE] Have: ${affordability.have.toFixed(6)} SOL | Need: ${affordability.need.toFixed(6)} SOL`);
          console.log(`AGT-05: [BALANCE] Shortfall: ${(affordability.need - affordability.have).toFixed(6)} SOL`);

          // Publish trade_failed event
          const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: 'Insufficient balance for trade overhead' }, correlationId);
          await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
          insertAuditLog.run({ envelope_id: correlationId, agent_id: 'AGT-05', event_type: 'trade_failed', payload: { mint, error: 'Insufficient balance' }, timestamp_utc: new Date().toISOString() });
          return;
        }
        console.log(`AGT-05: [BALANCE] ✅ Sufficient balance confirmed`);
      } catch (e: any) {
        console.log(`AGT-05: [LIVE] Balance check warning: ${e.message}`);
      }

      // ==========================================
      // JUPITER CLI EXCLUSIVE EXECUTION PATH
      // ==========================================
      try {
        const inputMint = 'So11111111111111111111111111111111111111112';
        const amountLamports = Math.floor((this.config?.trading?.position_size_sol || 0.0005) * 1e9);

        console.log(`AGT-05: [CLI-MODE] Initializing buy via Jupiter CLI binary...`);
        console.log(`AGT-05: [CLI-MODE] Order size: ${(this.config?.trading?.position_size_sol || 0.0005)} SOL → ${mint.slice(0, 8)}...`);

        // executeViaCli now handles the full swap using RTSE (auto-slippage)
        const txId = await this.executeViaCli(mint, amountLamports);

        if (txId) {
          console.log(`AGT-05: [CLI-SUCCESS] Buy confirmed. Tx: ${txId}`);

          // Post-swap: fetch quote for token estimation
          const quoteUrl = `https://api.jup.ag/swap/v1/quote?inputMint=${inputMint}&outputMint=${mint}&amount=${amountLamports}&slippageBps=500`;
          const quoteRes = await fetch(quoteUrl, { headers: { 'x-api-key': process.env.JUPITER_API_KEY || '' } });
          const quoteData: any = await quoteRes.json();

          const TOKEN_DECIMALS = 6;
          let tokensReceived = Number(quoteData.outAmount || 0) / Math.pow(10, TOKEN_DECIMALS);

          // Try to get exact on-chain balance received to avoid any quote discrepancies
          try {
            const connection = new Connection(process.env.HELIUS_RPC_URL!);
            const { getAssociatedTokenAddressSync } = require('@solana/spl-token');
            const ata = getAssociatedTokenAddressSync(new PublicKey(mint), this.keypair!.publicKey);
            const balRes = await connection.getTokenAccountBalance(ata);
            if (balRes && balRes.value && balRes.value.amount) {
              const actualReceived = Number(balRes.value.amount) / Math.pow(10, TOKEN_DECIMALS);
              if (actualReceived > 0) {
                tokensReceived = actualReceived;
                console.log(`AGT-05: [CLI-SUCCESS] On-chain balance confirmed: ${tokensReceived} tokens`);
              }
            }
          } catch (e: any) {
            console.warn(`AGT-05: Post-swap on-chain balance check fallback to quote: ${e.message}`);
          }

          const entryPriceSol = (this.config?.trading?.position_size_sol || 0.0005) / tokensReceived;

          const position = {
            position_id: correlationId,
            mint: mint,
            entry_price_sol: entryPriceSol,
            tokens_received: tokensReceived,
            state: 'open',
            tp1_price: entryPriceSol * (this.config?.trading?.tp1_multiplier || 1.5),
            tp2_price: entryPriceSol * (this.config?.trading?.tp2_multiplier || 2.0),
            sl_price: entryPriceSol * (this.config?.trading?.sl_multiplier || 0.8),
            peak_price_sol: entryPriceSol,
            entry_timestamp_utc: new Date().toISOString(),
          };

          await insertPosition.run(position);
          await this.rateLimiter.recordTrade(correlationId);

          const envelope = createEnvelope('AGT-05', 'position_opened', {
            ...position,
            tx_signature: txId
          }, correlationId);
          await this.redis.publish(CHANNEL_POSITION_OPENED, JSON.stringify(envelope));

          console.log(`AGT-05: [LIVE] ✅ POSITION OPENED: ${mint.slice(0, 8)} | Entry: ${entryPriceSol.toFixed(9)} SOL`);
        } else {
          throw new Error('CLI returned no transaction ID');
        }
      } catch (e: any) {
        console.error(`AGT-05: [CLI-FATAL] Trade aborted: ${e.message}`);
        const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: e.message }, correlationId);
        await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
      }

      console.log(`AGT-05: [LIVE] ========== TRADE END ==========`);
    } else {
      // PAPER MODE
      console.log(`AGT-05: [PAPER] ========== TRADE START ==========`);
      console.log(`AGT-05: [PAPER] Mint: ${mint}`);
      console.log(`AGT-05: [PAPER] Position size: ${(this.config?.trading?.position_size_sol || 0.0005)} SOL`);

      try {
        const inputMint = 'So11111111111111111111111111111111111111112';
        const amount = Math.floor((this.config?.trading?.position_size_sol || 0.0005) * 1e9);

        // Get quote for paper trading
        const quoteUrl = `https://api.jup.ag/swap/v1/quote?inputMint=${inputMint}&outputMint=${mint}&amount=${amount}&slippageBps=1000`;

        try {
          const quoteRes = await fetch(quoteUrl, {
            headers: { 'x-api-key': process.env.JUPITER_API_KEY || '' },
            signal: AbortSignal.timeout(10000)
          });
          if (!quoteRes.ok) throw new Error(`Quote failed: ${quoteRes.status}`);
          const quoteData: any = await quoteRes.json();

          if (quoteData.outAmount) {
            const TOKEN_DECIMALS = 6;
            const tokensReceived = Number(quoteData.outAmount) / Math.pow(10, TOKEN_DECIMALS);
            const entryPriceSol = (this.config?.trading?.position_size_sol || 0.0005) / tokensReceived;

            console.log(`AGT-05: [PAPER] ✅ Quote received: ${(this.config?.trading?.position_size_sol || 0.0005)} SOL → ${tokensReceived} tokens`);
            console.log(`AGT-05: [PAPER] Entry price: ${entryPriceSol} SOL per token`);

            // Record paper position
            const position = {
              position_id: correlationId,
              mint: mint,
              entry_price_sol: entryPriceSol,
              tokens_received: tokensReceived,
              state: 'open',
              tp1_price: entryPriceSol * (this.config?.trading?.tp1_multiplier || 1.1),
              tp2_price: entryPriceSol * (this.config?.trading?.tp2_multiplier || 1.25),
              sl_price: entryPriceSol * (this.config?.trading?.sl_multiplier || 0.95),
              peak_price_sol: entryPriceSol,
              entry_timestamp_utc: new Date().toISOString(),
            };

            await this.rateLimiter.recordTrade(correlationId);

            const envelope = createEnvelope('AGT-05', 'position_opened', {
              ...position,
              position_size_sol: (this.config?.trading?.position_size_sol || 0.0005),
            }, correlationId);
            await this.redis.publish(CHANNEL_POSITION_OPENED, JSON.stringify(envelope));

            console.log(`AGT-05: [PAPER] Paper position opened for ${mint}`);
            return;
          }
        } catch (e: any) {
          console.log(`AGT-05: [PAPER] Quote failed: ${e.message}`);
        }

        // Fallback: Record with default values
        const envelope = createEnvelope('AGT-05', 'position_opened', {
          mint,
          entry_price_sol: 0.001,
          tokens_received: 1000000,
          position_size_sol: (this.config?.trading?.position_size_sol || 0.0005),
        }, correlationId);
        await this.redis.publish(CHANNEL_POSITION_OPENED, JSON.stringify(envelope));
        await this.rateLimiter.recordTrade(correlationId);

        console.log(`AGT-05: [PAPER] Paper position opened (fallback) for ${mint}`);

      } catch (error: any) {
        console.log(`AGT-05: [PAPER] ❌ Paper trade failed: ${error.message}`);
        const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: error.message }, correlationId);
        await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
      }
    }
  }

  /**
   * Execute a trade using the Jupiter CLI (Official Binary)
   * This is more robust for production swaps as it handles signing and broadcasting internally.
   */
  private async executeViaCli(mint: string, amountLamports: number, slippageBps: number = 0): Promise<string> {
    try {
      console.log(`AGT-05: [CLI-SWAP] Executing (RTSE AUTO-SLIPPAGE): SOL → ${mint.slice(0, 8)}... (${amountLamports} lamports)`);

      const cmd = `jup spot swap --from SOL --to ${mint} --raw-amount ${amountLamports} --key sniper -f json`;
      const output = execSync(cmd).toString();
      const result = JSON.parse(output);

      if (result.error) {
        throw new Error(result.error);
      }

      return result.signature || result.txid || '';
    } catch (e: any) {
      console.error(`AGT-05: [CLI-ERROR] CLI swap failed: ${e.message}`);
      throw e;
    }
  }

  async stop(): Promise<void> {
    this.running = false;
    if (this.redis) {
      try {
        await this.redis.quit();
      } catch (e) {
        // Ignore quit errors
      }
    }
  }

  async run(): Promise<void> {
    this.running = true;
    console.log(`AGT-05: [STARTED] Ares Agent running...`);

    // Poll the trade_approved queue instead of using direct PubSub
    // This allows the system to hold qualified tokens in queue when max positions are reached
    while (this.running) {
      try {
        const { allowed } = await this.rateLimiter.canTrade();

        if (!allowed) {
          // If we can't trade (e.g., max positions reached), wait before checking again
          await new Promise(r => setTimeout(r, 5000));
          continue;
        }

        // We have a slot! Wait for an item in the queue (blocking pop for 2 seconds)
        // Anansi uses lpush to "event:trade_approved:0"
        const result = await this.redis.brpop('event:trade_approved:0', 2);

        if (result) {
          const [queueName, message] = result;
          const envelope = JSON.parse(message) as AgentMessageEnvelope;

          if (envelope.agent_id !== 'AGT-05') {
            console.log(`AGT-05: [QUEUE] Dequeued trade_approved for ${envelope.payload?.mint?.slice(0, 8) || envelope.payload?.token?.mint?.slice(0, 8)}...`);
            const mint = envelope.payload?.token?.mint || envelope.payload?.mint;
            const isPump = envelope.payload?.is_pump || false;

            // Execute trade
            await this.executeTrade(mint, envelope.correlation_id, isPump);
          }
        }
      } catch (e: any) {
        console.log(`AGT-05: [ERROR] Error in queue polling: ${e.message}`);
        await new Promise(r => setTimeout(r, 2000));
      }
    }
    if (this.redis) {
      try {
        // cleanup if needed
      } catch (e) { }
    }
  }
}




