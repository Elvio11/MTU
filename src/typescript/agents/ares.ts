import { Keypair, Transaction, TransactionInstruction, PublicKey } from '@solana/web3.js';
import { QuoteResponse, SwapApi } from '@jup-ag/api';
import { Connection, VersionedTransaction, VersionedMessage } from '@solana/web3.js';
import { AgentMessageEnvelope, createEnvelope, EventType } from '../shared/envelope';
import { loadKeypairFromKeystore } from '../shared/keystore';
import { CircuitBreaker } from '../shared/circuit-breaker';
import { isOperationalWindowActive } from '../shared/operational-window';
import { CHANNEL_TRADE_APPROVED, CHANNEL_TRADE_FAILED, CHANNEL_POSITION_OPENED } from '../shared/channels';
import Redis from 'ioredis';
import { createRedisClient } from '../shared/redis';
import dotenv from 'dotenv';
import axios from 'axios';
import { insertPosition, updatePosition, insertAuditLog } from '../shared/db';
import * as fs from 'fs';
import * as yaml from 'js-yaml';
import * as path from 'path';

dotenv.config();

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const MAX_SLIPPAGE_BPS = 1500;
const SLIPPAGE_LADDER = [500, 1000, 1500];
const RETRY_DELAYS = [0, 500, 1000];

// Dynamic Balance Guard constants
const RENT_ATA = 2039280;    // 0.00204 SOL - Rent for new Token ATA
const RENT_WSOL = 0;          // 0.0 SOL - Wallet likely has wSOL already
const FEE_BUFFER = 50000000;   // 0.0005 SOL - Buffer for network fees


// Helper: Determine which Jupiter API to use based on USD value
async function getJupiterApiVersion(positionSizeSol: number): Promise<{ version: 'v1' | 'v2', usdValue: number }> {
  const solPrice = await getSolPriceUsd();
  const usdValue = positionSizeSol * solPrice;
  
  if (usdValue < 6) {
    return { version: 'v1', usdValue };
  } else {
    return { version: 'v2', usdValue };
  }
}

// Helper: Check if wallet can afford the trade
async function canAffordTrade(
  connection: Connection,
  walletPubkey: any,
  positionSol: number
): Promise<{ ok: boolean; have: number; need: number; breakdown: string }> {
  const LAMPORTS_PER_SOL = 1_000_000_000;
  const balance = await connection.getBalance(walletPubkey);
  
  const positionLamports = positionSol * LAMPORTS_PER_SOL;
  // Estimate: Trade amount + rent for wSOL + rent for token ATA + fee buffer
  // Note: May need 2 ATAs if both wSOL and token are new
  const totalNeed = positionLamports + RENT_WSOL + RENT_ATA + FEE_BUFFER;
  
  const haveSol = balance / LAMPORTS_PER_SOL;
  const needSol = totalNeed / LAMPORTS_PER_SOL;
  const breakdown = `Position: ${positionSol} SOL + Rent: ${(RENT_WSOL+RENT_ATA)/LAMPORTS_PER_SOL} SOL + Buffer: ${FEE_BUFFER/LAMPORTS_PER_SOL} SOL = ${needSol.toFixed(6)} SOL`;
  
  return {
    ok: balance >= totalNeed,
    have: haveSol,
    need: needSol,
    breakdown
  };
}

// TP/SL Monitoring Helper Functions (used by Sentinel via shared module)
async function fetchTokenPrice(mint: string): Promise<number> {
  try {
    const resp = await fetch(`https://api.jup.ag/price/v3?ids=${mint}`, { 
      signal: AbortSignal.timeout(5000) 
    });
    const data: any = await resp.json();
    return data?.data?.[mint]?.price || 0;
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

  private config: any; constructor(redis: Redis, config: any) { this.redis = redis; this.config = config;
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
  try {
    const response = await fetch('https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112', {
      signal: AbortSignal.timeout(5000)
    });
    if (!response.ok) throw new Error(`Price fetch failed: ${response.status}`);
    const data: any = await response.json();
    const price = data?.data?.So11111111111111111111111111111111111111112?.price;
    if (price && typeof price === 'number' && price > 0) {
      return price;
    }
    throw new Error('No price in response');
  } catch (e) {
    console.log(`AGT-05: [PRICE] Using fallback SOL price: $200`);
    return 200; // Fallback to approximate price
  }
}

let lastRequestTime = 0;
const MIN_REQUEST_INTERVAL_MS = 1000;  // 1 second between Jupiter requests

export async function rateLimitedRequest<T>(requestFn: (baseUrl: string) => Promise<T>, config?: any): Promise<T> {
  const baseUrl = config?.trading?.jupiter_api_url || 'https://quote-api.jup.ag/v6';
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

  async init(): Promise<void> {
    this.redis = await createRedisClient();
    this.rateLimiter = new RateLimiter(this.redis, this.config);
    console.log('[RateLimiter] Initialized');
  }

  async loadSniperWallet(passphrase: string): Promise<void> {
    const keystorePath = process.env.SNIPER_KEYSTORE_PATH || './keystores/sniper.keystore';
    this.keypair = await loadKeypairFromKeystore(keystorePath, passphrase);
    console.log(`AGT-05: Loaded Sniper Wallet: ${this.keypair.publicKey.toBase58()}`);
    
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

      try {
        const inputMint = 'So11111111111111111111111111111111111111112'; // 43 chars - Jupiter format
        const amount = Math.floor((this.config?.trading?.position_size_sol || 0.0005) * 1e9);

        // Get actual SOL price and determine API version
        const apiInfo = await getJupiterApiVersion((this.config?.trading?.position_size_sol || 0.0005));
        const usdValue = apiInfo.usdValue;

        console.log(`AGT-05: [SMART ROUTING] Order value: $${usdValue.toFixed(2)} (${(this.config?.trading?.position_size_sol || 0.0005)} SOL) - Using ${apiInfo.version.toUpperCase()} API`);

        let tokensReceived = 0;
        let entryPriceSol = 0;
        let signedTxBytes: Uint8Array | null = null;
        let txId = '';
        const connection = new Connection(process.env.HELIUS_RPC_URL!);

        if (usdValue < 6) {
          // ==========================================
          // PATH 1: v1 API (fetch) for orders < $6
          // ==========================================
          console.log(`AGT-05: [V1-BUY] Using v1 API (<$6): ${(this.config?.trading?.position_size_sol || 0.0005)} SOL → ${mint.slice(0, 8)}...`);

          // Try slippage ladder: 10% → 15% → 20%
          let quoteData: any = null;
          for (const slippageBps of SLIPPAGE_LADDER) {
            console.log(`AGT-05: [V1-BUY] Requesting quote with slippage: ${slippageBps / 100}%`);
            const quoteParams = new URLSearchParams({
              inputMint: inputMint,
              outputMint: mint,
              amount: String(amount),
              slippageBps: String(slippageBps),
              onlyDirectRoutes: 'false',
              asLegacyTransaction: 'false',
            });

            try {
              const quoteUrl = `https://api.jup.ag/swap/v1/quote?${quoteParams}`;
              console.log(`AGT-05: [V1-BUY] URL: ${quoteUrl}`);
              
              const quoteRes = await fetch(quoteUrl, {
                signal: AbortSignal.timeout(10000),
              });

              const responseText = await quoteRes.text();
              console.log(`AGT-05: [V1-BUY] Response status: ${quoteRes.status}, body: ${responseText.substring(0, 200)}`);
              
              if (!quoteRes.ok) throw new Error(`V1 quote failed: ${quoteRes.status}`);
              quoteData = JSON.parse(responseText);

              if (quoteData.outAmount) {
                console.log(`AGT-05: [V1-BUY] ✅ Quote received with ${slippageBps / 100}% slippage`);
                break;
              }
            } catch (e: any) {
              console.log(`AGT-05: [V1-BUY] Quote failed with ${slippageBps / 100}% slippage: ${e.message}`);
            }
          }

          if (!quoteData || !quoteData.outAmount) {
            console.log(`AGT-05: [V1-BUY] ❌ No Jupiter quote with any slippage level`);
            const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: 'No quote with slippage ladder' }, correlationId);
            await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
            console.log(`AGT-05: [LIVE] ========== TRADE END ==========`);
            return;
          }

          // Fix: Pump.fun tokens have 6 decimals
          const TOKEN_DECIMALS = 6;
          tokensReceived = Number(quoteData.outAmount) / Math.pow(10, TOKEN_DECIMALS);
          entryPriceSol = (this.config?.trading?.position_size_sol || 0.0005) / tokensReceived;

          console.log(`AGT-05: [V1-BUY] ✅ Quote: ${(this.config?.trading?.position_size_sol || 0.0005)} SOL → ${tokensReceived} tokens`);
          console.log(`AGT-05: [V1-BUY] Entry price: ${entryPriceSol} SOL per token`);

          // Execute swap via v1 POST
          console.log(`AGT-05: [V1-BUY] Building swap transaction...`);

          const swapResponse: any = await rateLimitedRequest(async () => {
            const resp = await fetch('https://api.jup.ag/swap/v1/swap', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' }, // CRITICAL: Without this, Jupiter may fail to parse userPublicKey
              body: JSON.stringify({
                quoteResponse: quoteData,
                userPublicKey: this.keypair!.publicKey.toBase58(),
                wrapUnwrapSOL: true,
                prioritizationFeeLamports: 100000,
                maxPrioritizationFeeLamports: 100000,  // Cap at 0.001 SOL
              }),
              signal: AbortSignal.timeout(15000),
            });

            if (!resp.ok) throw new Error(`V1 swap failed: ${resp.status}`);
            return resp.json();
          });

          if (!swapResponse.swapTransaction) {
            throw new Error('No swap transaction returned');
          }

          // Deserialize and sign
          const swapTxBase64 = swapResponse.swapTransaction;
          const txBytes = Buffer.from(swapTxBase64, 'base64');
          
          // Try to deserialize as VersionedTransaction first
          let versionedTx: VersionedTransaction | null = null;
          let legacyTx: Transaction | null = null;
          
          try {
            versionedTx = VersionedTransaction.deserialize(txBytes);
            console.log(`AGT-05: [V1-BUY] Transaction type: Versioned (${versionedTx.message?.version || 'unknown'})`);
          } catch (e: any) {
            console.log(`AGT-05: [V1-BUY] Versioned parse error: ${e.message}, trying legacy...`);
            // For legacy transactions, we need to deserialize manually
            try {
              legacyTx = Transaction.from(txBytes);
              console.log(`AGT-05: [V1-BUY] Transaction type: Legacy`);
            } catch (e2: any) {
              console.log(`AGT-05: [V1-BUY] Legacy parse also failed: ${e2.message}`);
            }
          }
          
          if (versionedTx) {
            // Check original blockhash - Jupiter already provides valid blockhash (DO NOT OVERWRITE - for logging only)
            console.log(`AGT-05: [V1-BUY] Original blockhash from Jupiter: ${versionedTx.message.recentBlockhash?.slice(0, 10) || 'none'} (DO NOT OVERWRITE - for logging only)`);
            console.log(`AGT-05: [V1-BUY] Message version: ${versionedTx.message.version}`);
            
            // DO NOT get fresh blockhash - Jupiter's transaction is already compiled with valid blockhash!
            // Overwriting recentBlockhash corrupts the message buffer and invalidates the signature
            
            // Sign - just call sign directly without modifying signatures first
            versionedTx.sign([this.keypair!]);
            
            // Verify signature length is exactly 64 bytes
            const sigLength = versionedTx.signatures[0].length;
            console.log(`AGT-05: [V1-BUY] Signature length: ${sigLength} bytes (must be 64)`);
            if (sigLength !== 64) {
              console.log(`AGT-05: [V1-BUY] ❌ CRITICAL: Signature length invalid!`);
            }
            
            signedTxBytes = versionedTx.serialize();  // Use native Uint8Array
            console.log(`AGT-05: [V1-BUY] Signed tx size: ${signedTxBytes.length} bytes`);
            
            // Verify by deserializing again to confirm it's valid
            try {
              const verifyTx = VersionedTransaction.deserialize(signedTxBytes);
              console.log(`AGT-05: [V1-BUY] Verified: signatures=${verifyTx.signatures.length}, blockhash=${verifyTx.message.recentBlockhash?.slice(0, 10)}...`);
            } catch (e: any) {
              console.log(`AGT-05: [V1-BUY] Verification failed: ${e.message}`);
            }
          } else if (legacyTx) {
            // Jupiter's transaction already has valid blockhash - DO NOT OVERWRITE (for logging only)
            console.log(`AGT-05: [V1-BUY] Legacy transaction blockhash: ${legacyTx.recentBlockhash?.slice(0, 10) || 'none'} (DO NOT OVERWRITE)`);
            
            // Sign legacy transaction
            legacyTx.sign(this.keypair!);
            
            // Legacy signatures are SignaturePubkeyPair objects - verify signature bytes
            const legacySig = legacyTx.signatures[0].signature;
            const legacySigLength = legacySig ? legacySig.length : 0;
            console.log(`AGT-05: [V1-BUY] Legacy signature length: ${legacySigLength} bytes (must be 64)`);
            
            signedTxBytes = legacyTx.serialize();
            console.log(`AGT-05: [V1-BUY] Signed legacy tx size: ${signedTxBytes.length} bytes`);
          }
          
          console.log(`AGT-05: [V1-BUY] Wallet pubkey: ${this.keypair!.publicKey.toBase58()}`);

        } else {
          // ==========================================
          // PATH 2: v2 API for orders >= $6
          // ==========================================
          console.log(`AGT-05: [V2-BUY] Using v2 API (>=$6): ${(this.config?.trading?.position_size_sol || 0.0005)} SOL → ${mint.slice(0, 8)}...`);

          try {
            // Step 1: Get quote + assembled transaction via /order
            // NOTE: Not passing slippageBps to enable Jupiter's RTSE (Real-Time Slippage Estimator)
            const orderUrl = 'https://api.jup.ag/swap/v2/order';
            const orderRes = await fetch(`${orderUrl}?${new URLSearchParams({
              inputMint: inputMint,
              outputMint: mint,
              amount: String(amount),
              taker: this.keypair!.publicKey.toBase58(),
              mode: 'fast',
              // slippageBps removed to enable RTSE auto-slippage
            })}`, {
              signal: AbortSignal.timeout(10000),
            });

            if (!orderRes.ok) throw new Error(`V2 order failed: ${orderRes.status}`);
            const orderData: any = await orderRes.json();

            if (!orderData.transaction) {
              throw new Error('V2: No transaction in order response');
            }

            // Step 2: Sign transaction
            const txBytes = Buffer.from(orderData.transaction, 'base64');
            const versionedTx = VersionedTransaction.deserialize(txBytes);
            versionedTx.sign([this.keypair!]);
            signedTxBytes = Buffer.from(versionedTx.serialize());

            // Step 3: Execute via /execute (managed execution)
            const executeRes = await fetch('https://api.jup.ag/swap/v2/execute', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                signedTransaction: Buffer.from(signedTxBytes).toString('base64'),  // Uint8Array to base64
                requestId: orderData.requestId,
                prioritizationFeeLamports: 100000,
                maxPrioritizationFeeLamports: 100000,  // Cap at 0.001 SOL
              }),
              signal: AbortSignal.timeout(15000),
            });

            if (!executeRes.ok) throw new Error(`V2 execute failed: ${executeRes.status}`);
            const executeData: any = await executeRes.json();

            if (executeData.status === 'Success') {
              txId = executeData.signature;
              console.log(`AGT-05: [V2-BUY] ✅ Executed via /execute: ${txId}`);

              // Fix: Calculate tokens received (v2 returns outAmount in proper units)
              if (executeData.outAmount) {
                const TOKEN_DECIMALS = 6;
                tokensReceived = Number(executeData.outAmount) / Math.pow(10, TOKEN_DECIMALS);
                entryPriceSol = (this.config?.trading?.position_size_sol || 0.0005) / tokensReceived;
              }
            } else {
              throw new Error(`V2 execution failed: ${JSON.stringify(executeData)}`);
            }

          } catch (v2Error: any) {
            console.log(`AGT-05: [V2-BUY] ❌ v2 failed, falling back to v1: ${v2Error.message}`);

            // FALLBACK: Try v1 API
            console.log(`AGT-05: [FALLBACK] Using v1 API fallback...`);

            const quoteParams = new URLSearchParams({
              inputMint: inputMint,
              outputMint: mint,
              amount: String(amount),
              slippageBps: String(SLIPPAGE_LADDER[0]),
              onlyDirectRoutes: 'false',
              asLegacyTransaction: 'false',
            });

            const quoteRes = await fetch(`https://api.jup.ag/swap/v1/quote?${quoteParams}`, {
              signal: AbortSignal.timeout(10000),
            });

            if (!quoteRes.ok) throw new Error(`Fallback v1 quote failed: ${quoteRes.status}`);
            const quoteData: any = await quoteRes.json();

            if (!quoteData.outAmount) throw new Error('Fallback v1: No quote available');

            const TOKEN_DECIMALS = 6;
            tokensReceived = Number(quoteData.outAmount) / Math.pow(10, TOKEN_DECIMALS);
            entryPriceSol = (this.config?.trading?.position_size_sol || 0.0005) / tokensReceived;

            const swapResponse = await fetch('https://api.jup.ag/swap/v1/swap', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                quoteResponse: quoteData,
                userPublicKey: this.keypair!.publicKey.toBase58(),
                wrapUnwrapSOL: true,
                prioritizationFeeLamports: 100000,
                maxPrioritizationFeeLamports: 100000,  // Cap at 0.001 SOL
              }),
              signal: AbortSignal.timeout(15000),
            });

            if (!swapResponse.ok) throw new Error(`Fallback v1 swap failed: ${swapResponse.status}`);
            const swapData: any = await swapResponse.json();

            if (!swapData.swapTransaction) throw new Error('Fallback v1: No transaction returned');

            const txBytes = Buffer.from(swapData.swapTransaction, 'base64');
            const versionedTx = VersionedTransaction.deserialize(txBytes);
            versionedTx.sign([this.keypair!]);
            signedTxBytes = Buffer.from(versionedTx.serialize());
          }
        }

        if (!signedTxBytes) {
          throw new Error('No signed transaction available');
        }

        // If txId not set (v1 path), broadcast via RPC
        if (!txId) {
          // Broadcast to RPC providers (skip empty URLs)
          // Add public RPC as fallback
          const RPC_PROVIDERS = [
            { name: 'Helius', url: process.env.HELIUS_RPC_URL! },
            { name: 'Public', url: 'https://api.mainnet-beta.solana.com' },
            ...(process.env.QUICKNODE_RPC_URL ? [{ name: 'QuickNode', url: process.env.QUICKNODE_RPC_URL }] : []),
            { name: 'Alchemy', url: process.env.ALCHEMY_RPC_URL! },
          ];

          console.log(`AGT-05: [LIVE] Broadcasting to ${RPC_PROVIDERS.length} RPC providers...`);

          const broadcastPromises = RPC_PROVIDERS.map(async (provider) => {
            try {
              console.log(`AGT-05: [LIVE] Broadcasting to ${provider.name}...`);
              const conn = new Connection(provider.url, {
                commitment: 'confirmed',
                confirmTransactionInitialTimeout: 60000,
              });
              
              // Try with maxRetries and proper options
              const txId = await conn.sendRawTransaction(signedTxBytes, {
                skipPreflight: false,
                preflightCommitment: 'processed',
                maxRetries: 5,
              });
              console.log(`AGT-05: [LIVE] ${provider.name} sent tx: ${txId}`);
              return { name: provider.name, txId, success: true };
            } catch (e: any) {
              console.log(`AGT-05: [LIVE] ${provider.name} failed: ${e.message}`);
              if (e.message.includes('Simulation failed')) {
                console.log(`AGT-05: [LIVE] ${provider.name} simulation error - trying with maxRetries...`);
                try {
                  const conn = new Connection(provider.url);
                  const txId = await conn.sendRawTransaction(signedTxBytes, {
                    skipPreflight: true,
                    maxRetries: 5,
                  });
                  console.log(`AGT-05: [LIVE] ${provider.name} sent with retries: ${txId}`);
                  return { name: provider.name, txId, success: true };
                } catch (e2: any) {
                  console.log(`AGT-05: [LIVE] ${provider.name} also failed: ${e2.message}`);
                }
              }
              return { name: provider.name, error: e.message, success: false };
            }
          });

          const results = await Promise.allSettled(broadcastPromises);

          // Find first successful broadcast
          let txId = '';
          for (const result of results) {
            if (result.status === 'fulfilled' && result.value.success && result.value.txId) {
              txId = result.value.txId;
              console.log(`AGT-05: [LIVE] ✅ ${result.value.name} broadcast success: ${txId}`);
              break;
            }
          }

          if (!txId) {
            // All failed - check if any have pending tx
            for (const result of results) {
              if (result.status === 'fulfilled' && result.value.txId) {
                txId = result.value.txId;
                break;
              }
            }
          }

          if (!txId) {
            // Try Jupiter's execute endpoint as fallback - they handle retries better
            console.log(`AGT-05: [LIVE] Trying Jupiter /execute endpoint as fallback...`);
            try {
              const signedBase64 = Buffer.from(signedTxBytes).toString('base64');
              const executeRes = await fetch('https://api.jup.ag/swap/v2/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  signedTransaction: signedBase64,
                  requestId: `mtus-${Date.now()}`,
                  prioritizationFeeLamports: 100000,
                  maxPrioritizationFeeLamports: 100000,  // Cap at 0.001 SOL
                }),
                signal: AbortSignal.timeout(60000),
              });
              
              if (executeRes.ok) {
                const executeData: any = await executeRes.json();
                console.log(`AGT-05: [LIVE] Jupiter execute response: ${JSON.stringify(executeData)}`);
                if (executeData.signature) {
                  txId = executeData.signature;
                  console.log(`AGT-05: [LIVE] ✅ Jupiter execute success: ${txId}`);
                }
              } else {
                const errText = await executeRes.text();
                console.log(`AGT-05: [LIVE] Jupiter execute failed: ${executeRes.status} - ${errText}`);
              }
            } catch (e: any) {
              console.log(`AGT-05: [LIVE] Jupiter execute error: ${e.message}`);
            }
          }

          if (!txId) {
            console.log(`AGT-05: [LIVE] ❌ All RPC broadcasts failed`);
            throw new Error('All RPC providers failed to broadcast');
          }

          console.log(`AGT-05: [LIVE] Transaction broadcast successful: ${txId}`);

          // Wait for confirmation using primary RPC (Helius)
          console.log(`AGT-05: [LIVE] Waiting for confirmation (60s timeout)...`);
          const connection = new Connection(process.env.HELIUS_RPC_URL!);
          let confirmed = false;
          let confirmationStatus = 'unknown';
          const startTime = Date.now();
          while (Date.now() - startTime < 60000) {
            try {
              // Use searchTransactionHistory to find the transaction
              const status = await connection.getSignatureStatus(txId, { searchTransactionHistory: true });
              console.log(`AGT-05: [LIVE] Signature status: ${JSON.stringify(status.value)}`);
              confirmationStatus = status.value?.confirmationStatus || 'unknown';
              
              // Check for errors FIRST - even if confirmed, if there's an error, it's a failed transaction
              const errInfo = status.value?.err || (status.value as any)?.status?.Err;
              if (errInfo) {
                console.log(`AGT-05: [LIVE] ❌ Transaction failed with error: ${JSON.stringify(errInfo)}`);
                confirmed = false;
                break;
              }
              
              if (status.value?.confirmationStatus === 'confirmed' || status.value?.confirmationStatus === 'finalized') {
                confirmed = true;
                console.log(`AGT-05: [LIVE] ✅ Transaction confirmed successfully!`);
                break;
              }
            } catch (e: any) {
              console.log(`AGT-05: [LIVE] Status check error: ${e.message}`);
            }
            await new Promise(r => setTimeout(r, 2000));
          }

          if (!confirmed) {
            console.log(`AGT-05: [LIVE] ⚠️ Transaction not confirmed within 60s. Status: ${confirmationStatus}`);
            
            // Last resort: Try Jupiter execute endpoint
            console.log(`AGT-05: [LIVE] Last attempt: Trying Jupiter execute endpoint...`);
            try {
              const signedBase64 = Buffer.from(signedTxBytes).toString('base64');
              const executeRes = await fetch('https://api.jup.ag/swap/v2/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  signedTransaction: signedBase64,
                  requestId: `mtus-final-${Date.now()}`,
                  prioritizationFeeLamports: 100000,
                  maxPrioritizationFeeLamports: 100000,  // Cap at 0.001 SOL
                }),
                signal: AbortSignal.timeout(90000),
              });
              
              if (executeRes.ok) {
                const executeData: any = await executeRes.json();
                console.log(`AGT-05: [LIVE] Jupiter execute response: ${JSON.stringify(executeData)}`);
                if (executeData.signature && (executeData.status === 'Success' || executeData.code === 0)) {
                  txId = executeData.signature;
                  confirmed = true;
                  console.log(`AGT-05: [LIVE] ✅ Jupiter execute SUCCESS: ${txId}`);
                }
              } else {
                const errText = await executeRes.text();
                console.log(`AGT-05: [LIVE] Jupiter execute failed: ${executeRes.status} - ${errText}`);
              }
            } catch (e: any) {
              console.log(`AGT-05: [LIVE] Jupiter execute error: ${e.message}`);
            }
            
            if (!confirmed) {
              // Don't record position if transaction failed
              const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: 'Transaction failed: ' + confirmationStatus, txId }, correlationId);
              await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
              console.log(`AGT-05: [LIVE] ❌ Trade failed - not recording position`);
              console.log(`AGT-05: [LIVE] ========== TRADE END ==========`);
              
              // Remove from active positions set since trade failed
              await this.redis.srem('mtus:active_positions', correlationId);
              return;
            } else {
              console.log(`AGT-05: [LIVE] ✅ Transaction confirmed successfully: ${txId}`);
            }
          }
        }

        // Record position with real tx signature
        var txSignature = txId;

        // Record position
        try {
          insertPosition.run({
            position_id: correlationId,
            mint: mint,
            token_name: 'LIVE_TOKEN',
            token_symbol: 'LIVE',
            entry_price_sol: entryPriceSol,
            entry_amount_sol: (this.config?.trading?.position_size_sol || 0.0005),
            tokens_received: tokensReceived,
            entry_tx_signature: txSignature,
            entry_timestamp_utc: new Date().toISOString(),
            state: 'OPEN',
            tp1_price: entryPriceSol * (this.config?.trading?.tp1_multiplier || 2.0),
            tp2_price: entryPriceSol * (this.config?.trading?.tp2_multiplier || 5.0),
            sl_price: entryPriceSol * (this.config?.trading?.sl_multiplier || 0.7),
            peak_price_sol: entryPriceSol,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          });
          
          // Audit log
          insertAuditLog.run({
            envelope_id: correlationId,
            agent_id: 'AGT-05',
            event_type: 'position_opened',
            payload: { mint, entry_price_sol: entryPriceSol, tokens_received: tokensReceived, tx_signature: txSignature },
            timestamp_utc: new Date().toISOString()
          });
        } catch (e) {
          console.log(`AGT-05: [LIVE] DB insert note: ${e}`);
        }

        const envelope = createEnvelope('AGT-05', 'position_opened', {
          mint,
          entry_price_sol: entryPriceSol,
          tokens_received: tokensReceived,
          position_size_sol: (this.config?.trading?.position_size_sol || 0.0005),
        }, correlationId);
        await this.redis.publish(CHANNEL_POSITION_OPENED, JSON.stringify(envelope));

        // Record trade for rate limiting
        await this.rateLimiter.recordTrade(correlationId);

        console.log(`AGT-05: [LIVE] Position opened for ${mint}`);

      } catch (swapError: any) {
        console.log(`AGT-05: [LIVE] ⚠️ Swap execution failed: ${swapError.message}`);
        // Don't record position if swap fails
        const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: swapError.message }, correlationId);
        await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
        console.log(`AGT-05: [LIVE] ========== TRADE END ==========`);
        return;
      }

    } else {
      // PAPER MODE
      console.log(`AGT-05: [PAPER] ========== TRADE START ==========`);
      console.log(`AGT-05: [PAPER] Mint: ${mint}`);
      console.log(`AGT-05: [PAPER] Position size: ${(this.config?.trading?.position_size_sol || 0.0005)} SOL`);

      try {
        const inputMint = 'So11111111111111111111111111111111111111112'; // 43 chars - Jupiter format
        const amount = Math.floor((this.config?.trading?.position_size_sol || 0.0005) * 1e9);

        // Get quote for paper trading
        const quoteUrl = `https://api.jup.ag/swap/v1/quote?inputMint=${inputMint}&outputMint=${mint}&amount=${amount}&slippageBps=1000`;

        try {
          const quoteRes = await fetch(quoteUrl, { signal: AbortSignal.timeout(10000) });
          if (!quoteRes.ok) throw new Error(`Quote failed: ${quoteRes.status}`);
            const quoteData: any = await quoteRes.json();

            if (quoteData.outAmount) {
            const TOKEN_DECIMALS = 6;
            const tokensReceived = Number(quoteData.outAmount) / Math.pow(10, TOKEN_DECIMALS);
            const entryPriceSol = (this.config?.trading?.position_size_sol || 0.0005) / tokensReceived;

            console.log(`AGT-05: [PAPER] ✅ Quote received: ${(this.config?.trading?.position_size_sol || 0.0005)} SOL → ${tokensReceived} tokens`);
            console.log(`AGT-05: [PAPER] Entry price: ${entryPriceSol} SOL per token`);

            // Record paper position
            const envelope = createEnvelope('AGT-05', 'position_opened', {
              mint,
              entry_price_sol: entryPriceSol,
              tokens_received: tokensReceived,
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

        console.log(`AGT-05: [PAPER] Paper position opened (fallback) for ${mint}`);

      } catch (error: any) {
console.log(`AGT-05: [PAPER] ❌ Paper trade failed: ${error.message}`);
        const envelope = createEnvelope('AGT-05', 'trade_failed', { mint, error: error.message }, correlationId);
        await this.redis.publish(CHANNEL_TRADE_FAILED, JSON.stringify(envelope));
      }
    }
  }

  stop() {
    this.running = false;
  }

async run(): Promise<void> {
    this.running = true;
    console.log(`AGT-05: [STARTED] Ares Agent running...`);

    // Subscribe to trade_approved for executed trades from Anansi
    const subscriber = this.redis.duplicate();
    
    subscriber.on('message', async (channel: string, message: string) => {
      if (channel !== CHANNEL_TRADE_APPROVED) return;
      
      try {
        const envelope = JSON.parse(message) as AgentMessageEnvelope;
        if (envelope.agent_id === 'AGT-05') return;

        // Execute trade directly when trade_approved arrives from Anansi
        // No queue dequeue - Hermes already processed the queue and Anansi approved it
        console.log(`AGT-05: [EVENT] Received trade_approved for ${envelope.payload?.mint?.slice(0, 8) || envelope.payload?.token?.mint?.slice(0, 8)}...`);
        const mint = envelope.payload?.token?.mint || envelope.payload?.mint;
        const isPump = envelope.payload?.is_pump || false;
        await this.executeTrade(mint, envelope.correlation_id, isPump);
      } catch (e: any) {
        console.log(`AGT-05: [ERROR] Error processing event: ${e.message}`);
      }
    });

    await subscriber.subscribe(CHANNEL_TRADE_APPROVED);
    console.log(`AGT-05: Subscribed to trade_approved channel`);

    // Keep running
    while (this.running) {
      await new Promise(r => setTimeout(r, 1000));
    }

    await subscriber.quit();
  }
}




