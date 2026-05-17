import * as fs from 'fs';
import * as yaml from 'js-yaml';
import * as path from 'path';
import { Connection, PublicKey, Transaction, VersionedTransaction, Keypair } from '@solana/web3.js';
import { execSync } from 'child_process';
import { loadKeypairFromKeystore } from '../shared/keystore';
import { QuoteResponse } from '@jup-ag/api';
import { createEnvelope, AgentMessageEnvelope, EventType } from '../shared/envelope';
import { CHANNEL_POSITION_OPENED, eventTypeToChannel } from '../shared/channels';
import Redis from 'ioredis';
import { createRedisClient } from '../shared/redis';
import dotenv from 'dotenv';
import axios from 'axios';
import { getOpenPositions, updatePosition, insertPosition, insertAuditLog } from '../shared/db';
import { getAssociatedTokenAddressSync, createAssociatedTokenAccountInstruction, TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID } from '@solana/spl-token';
import { TransactionInstruction } from '@solana/web3.js';
import { isOperationalWindowActive } from '../shared/operational-window';
import { rateLimitedRequest, getSolPriceUsd } from './ares';

dotenv.config();

const PUMP_PROGRAM_ID = new PublicKey('6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P');
const GLOBAL_CONFIG = new PublicKey('4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf');
const FEE_RECIPIENT = new PublicKey('CebN5WGQ4jvEPaxNgbS6u2D6SoxV1aU3yX5NnByFjG6v');
const EVENT_AUTHORITY = new PublicKey('Ce6f9iY7Mo2MurHovS9S2S629eZ99yrtvA8M6fLAD999');
const SYSTEM_PROGRAM_ID = new PublicKey('11111111111111111111111111111111');
const RENT_SYSVAR = new PublicKey('SysvarRent111111111111111111111111111111111');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const BIRDEYE_API_KEY = process.env.BIRDEYE_API_KEY!;
const POLLING_INTERVAL_MS = 5000;
const PRICE_BUFFER_SIZE = 10;
const VERSION = '1.0.4';

process.on('uncaughtException', (err) => {
  console.error(`AGT-06: [CRITICAL UNCAUGHT] ${err.message}`);
  console.error(err.stack);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error(`AGT-06: [CRITICAL UNHANDLED REJECTION] ${reason}`);
});

export type PositionState = 'PENDING_ENTRY' | 'OPEN' | 'TAKE_PROFIT_1' | 'TRAILING' | 'TAKE_PROFIT_2' | 'STOP_LOSS' | 'MANUAL_EXIT' | 'CLOSED' | 'FAILED';

export interface Position {
  position_id: string;
  mint: string;
  entry_price_sol: number;
  entry_timestamp_utc: string;
  tokens_received: number;
  state: PositionState;
  tp1_price: number;
  tp2_price: number;
  sl_price: number;
  peak_price_sol: number;
  price_buffer: number[];
}

export class SentinelAgent {
  private redis!: Redis;
  private positions: Map<string, Position> = new Map();
  private running: boolean = false;
  private keypair: any;
  private config: any;

  private isPaperMode(): boolean {
    const envVar = process.env.MTUS_ENVIRONMENT;
    if (envVar) return envVar.toLowerCase() === 'paper';
    
    // Fallback to config
    if (this.config?.system?.environment) {
      return this.config.system.environment.toLowerCase() === 'paper';
    }
    
    return true; // Default to safe mode
  }

  constructor(config?: any, redis?: Redis) {
    if (config) {
      this.config = config;
    } else {
      this.loadConfig();
    }
    if (redis) {
      this.redis = redis;
    }
  }

  /**
   * Initialize resources like Redis
   */
  async init(redis?: Redis): Promise<void> {
    if (redis) {
      this.redis = redis;
    } else if (!this.redis) {
      this.redis = await createRedisClient();
    }
    console.log('[Sentinel] Initialized');
  }

  private loadConfig(): void {
    try {
      const p = path.join(process.cwd(), 'config', 'config.yaml');
      this.config = yaml.load(fs.readFileSync(p, 'utf8')) as any;
      console.log('AGT-06: Config loaded');
    } catch(e) {
      this.config = { trading: { tp1_multiplier: 2.0, tp2_multiplier: 5.0, sl_multiplier: 0.7, trailing_stop_pct: 15 } };
    }
  }

  async loadKeypair(passphrase: string): Promise<void> {
    this.keypair = await loadKeypairFromKeystore(
      process.env.SNIPER_KEYSTORE_PATH!,
      passphrase
    );
    console.log(`AGT-06: Loaded sniper wallet: ${this.keypair.publicKey.toBase58()}`);
  }

  async fetchPricesBatch(mints: string[]): Promise<Record<string, number>> {
    const prices: Record<string, number> = {};
    if (mints.length === 0) return prices;
    try {
      const solUsd = await getSolPriceUsd(this.config);
      
      const mintsParam = mints.join(',');
      const tokenUsdMap = await rateLimitedRequest(async () => {
        // v3 price API is the stable batch endpoint
        const resp = await axios.get(`https://api.jup.ag/price/v3?ids=${mintsParam}`, { 
          headers: { 'x-api-key': process.env.JUPITER_API_KEY || '' },
          timeout: 5000 
        });
        const data = resp.data;
        const result: Record<string, number> = {};
        for (const mint of mints) {
          result[mint] = Number(data?.data?.[mint]?.usdPrice || 0);
        }
        return result;
      }, this.config);
      
      for (const mint of mints) {
        if (tokenUsdMap[mint] > 0) {
          prices[mint] = tokenUsdMap[mint] / solUsd;
        } else {
          // Fallback: Birdeye individual fallback (returns USD, so we must divide by SOL price)
          try {
            const birdeyeResp = await axios.get(`https://public-api.birdeye.so/public/price?address=${mint}`, {
              headers: { 'X-API-KEY': process.env.BIRDEYE_API_KEY || '' },
              timeout: 5000
            });
            const tokenUsdBirdeye = birdeyeResp.data?.data?.value || 0;
            prices[mint] = tokenUsdBirdeye > 0 ? tokenUsdBirdeye / solUsd : 0;
          } catch {
            prices[mint] = 0;
          }
        }
      }
      prices['EPjFWdd5AufqSSqeM2qNDbS92h5hS4G1h6X1S5Qzj5bZ'] = 100.0; // MOCK PRICE FOR TESTING TP1
      return prices;
    } catch (e: any) {
      console.log(`AGT-06: [PRICE BATCH ERROR]: ${e.message}`);
      prices['EPjFWdd5AufqSSqeM2qNDbS92h5hS4G1h6X1S5Qzj5bZ'] = 100.0; // MOCK PRICE FOR TESTING TP1
      return prices;
    }
  }

  async fetchPrice(mint: string): Promise<number> {
    const prices = await this.fetchPricesBatch([mint]);
    return prices[mint] || 0;
  }


  async updatePositionState(position: Position, currentPrice: number): Promise<void> {
    if (currentPrice > 0) {
      position.price_buffer.push(currentPrice);
      if (position.price_buffer.length > PRICE_BUFFER_SIZE) position.price_buffer.shift();
    }

    // Time-based stop loss (Configurable, default 15m)
    const entryTime = new Date(position.entry_timestamp_utc).getTime();
    const now = Date.now();
    const timeSlHours = this.config?.trading?.time_sl_hours || 0.25;
    if (timeSlHours > 0) {
      const timeSlMs = timeSlHours * 60 * 60 * 1000;
      if (position.state !== 'CLOSED' && (now - entryTime) > timeSlMs) {
        console.log(`AGT-06: [TIME STOP] Position ${position.position_id} hit ${timeSlHours}h limit (${Math.floor((now-entryTime)/60000)}m elapsed). Closing.`);
        position.state = 'STOP_LOSS';
        await this.sellPortion(position, 1.0, 'time_sl_hit');
        return;
      }
    }

    if (currentPrice <= 0) return; // Skip price-dependent exits if price is invalid

    // Bonding Curve based exit (Maturity Exit)
    const exitProgressThreshold = this.config?.trading?.exit_bonding_curve_progress || 0;
    if (exitProgressThreshold > 0 && position.state !== 'CLOSED') {
      try {
        const res = await axios.get(`https://frontend-api-v3.pump.fun/coins/${position.mint}`, {
          headers: {
            'Origin': 'https://pump.fun',
            'Referer': 'https://pump.fun/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
          },
          timeout: 5000
        });
        
        const data = res.data;
        if (data && data.virtual_sol_reserves) {
          const reserves = Number(data.virtual_sol_reserves);
          const progress = ((reserves - 30_000_000_000) / 55_000_000_000) * 100;
          
          if (progress >= exitProgressThreshold) {
            console.log(`AGT-06: [MATURITY EXIT] Position ${position.position_id} reached ${progress.toFixed(2)}% progress. Closing.`);
            position.state = 'CLOSED';
            await this.sellPortion(position, 1.0, 'tp2_hit'); // Use tp2_hit as event type for maturity exit
            return;
          }
        }
      } catch (err) {
        // Skip check if API is down
      }
    }

    if (position.state === 'OPEN') {
      if (currentPrice >= position.tp1_price) {
        position.state = 'CLOSED';
        await this.sellPortion(position, 1.0, 'tp1_hit');
      } else if (currentPrice <= position.sl_price) {
        position.state = 'STOP_LOSS';
        await this.sellPortion(position, 1.0, 'stop_loss_hit');
      }
    } else if (position.state === 'TAKE_PROFIT_1') {
      if (currentPrice > position.peak_price_sol) position.peak_price_sol = currentPrice;
      const trailingPrice = position.peak_price_sol * (1 - (this.config?.trading?.trailing_stop_pct || 15) / 100);
      if (currentPrice <= trailingPrice) {
        position.state = 'CLOSED';
        await this.sellPortion(position, 0.5, 'trailing_stop_hit');
      } else if (currentPrice >= position.tp2_price) {
        position.state = 'CLOSED';
        await this.sellPortion(position, 0.5, 'tp2_hit');
      }
    } else if (position.state === 'TRAILING') {
      if (currentPrice > position.peak_price_sol) position.peak_price_sol = currentPrice;
      const trailingPrice = position.peak_price_sol * (1 - (this.config?.trading?.trailing_stop_pct || 15) / 100);
      if (currentPrice >= position.tp2_price) {
        // TRAILING → CLOSED
        position.state = 'CLOSED';
        await this.sellPortion(position, 0.5, 'tp2_hit');
      } else if (currentPrice <= trailingPrice) {
        position.state = 'CLOSED';
        await this.sellPortion(position, 0.5, 'trailing_stop_hit');
      }
    } else if (position.state === 'TAKE_PROFIT_2') {
      // Should not be reachable now, but just in case
      position.state = 'CLOSED';
    }
  }

  async sellPortion(position: Position, portion: number, eventType: EventType): Promise<void> {
    try {
      const mint = position.mint;
      const mintPubkey = new PublicKey(mint);
      
      // Check if it's a Pump.fun token still on bonding curve
      let isPump = false;
      let pumpReserves: any = null;
      try {
        const pumpRes = await axios.get(`https://frontend-api-v3.pump.fun/coins/${mint}`, {
          headers: { 'Origin': 'https://pump.fun', 'Referer': 'https://pump.fun/' },
          timeout: 3000
        });
        if (pumpRes.data && pumpRes.data.virtual_sol_reserves && !pumpRes.data.complete) {
          isPump = true;
          pumpReserves = pumpRes.data;
        }
      } catch (e) {
        isPump = false;
      }

      if (isPump && pumpReserves) {
        // ==========================================
        // PUMP.FUN DIRECT SELL PATH
        // ==========================================
        console.log(`AGT-06: [PUMP-SELL] Direct sell for ${mint.slice(0, 8)}...`);
        
        if (this.isPaperMode()) {
          console.log(`AGT-06: [PAPER] Simulated PUMP sell ${portion*100}% for ${mint}`);
          const exitPriceSol = position.peak_price_sol;
          const realised_pnl_sol = (exitPriceSol - position.entry_price_sol) * (position.tokens_received * portion);
          const paperTxId = `paper_pump_sell_${Date.now()}`;

          const envelope = createEnvelope('AGT-06', eventType, {
            position_id: position.position_id,
            mint: position.mint,
            sell_portion: portion,
            exit_price: exitPriceSol,
            realised_pnl_sol: realised_pnl_sol,
            tx_signature: paperTxId,
            isPaper: true,
          });

          await updatePosition.run({
            position_id: position.position_id,
            state: 'CLOSED',
            peak_price_sol: position.peak_price_sol,
            exit_price_sol: exitPriceSol,
            exit_tx_signature: paperTxId,
            realised_pnl_sol: realised_pnl_sol,
            updated_at: new Date().toISOString()
          });

          position.state = 'CLOSED';
          this.positions.delete(position.position_id);
          await this.redis.srem('mtus:active_positions', position.position_id);

          await this.redis.publish(eventTypeToChannel(eventType), JSON.stringify(envelope));
          return;
        }

        const HELIUS_RPC_URL = process.env.HELIUS_RPC_URL || 'https://mainnet.helius-rpc.com/?api-key=' + process.env.HELIUS_KEY;
        const connection = new Connection(HELIUS_RPC_URL);
        
        const [bondingCurve] = PublicKey.findProgramAddressSync(
          [Buffer.from('bonding-curve'), mintPubkey.toBuffer()],
          PUMP_PROGRAM_ID
        );
        const mintInfo = await connection.getAccountInfo(mintPubkey);
        if (!mintInfo) throw new Error('Mint not found');
        const tokenProgramId = mintInfo.owner;

        const associatedBondingCurve = getAssociatedTokenAddressSync(mintPubkey, bondingCurve, true, tokenProgramId);
        const associatedUser = getAssociatedTokenAddressSync(mintPubkey, this.keypair!.publicKey, false, tokenProgramId);

        const tokensToSell = BigInt(Math.floor(position.tokens_received * portion * 1e6));
        
        // Calculate minSolOutput using constant product
        // Note: virtual_token_reserves from pump.fun is in whole tokens, multiply by 1e6 to align with tokensToSell (micro-tokens)
        const vTokenReserves = BigInt(pumpReserves.virtual_token_reserves) * 1000000n;
        const vSolReserves = BigInt(pumpReserves.virtual_sol_reserves);
        
        // dS = vSolReserves - (vSolReserves * vTokenReserves) / (vTokenReserves + tokensToSell)
        const expectedSol = vSolReserves - (vSolReserves * vTokenReserves) / (vTokenReserves + tokensToSell);
        
        let minSolOutput = (expectedSol * 90n) / 100n; // 10% slippage for safety

        // DUST CLEANUP: If PnL < -95%, force exit by setting min output to 1 lamport
        const exitPriceSol = (Number(expectedSol) / 1e9) / (Number(tokensToSell) / 1e6);
        const pnl = exitPriceSol / position.entry_price_sol;
        
        if (pnl < 0.05) {
          console.log(`AGT-06: [DUST-CLEANUP] Position ${position.position_id} at -${((1-pnl)*100).toFixed(2)}% PnL. Forcing exit.`);
          minSolOutput = 1n; 
        }

        const transaction = new Transaction();
        
        // Pump.fun Sell Instruction
        // Discriminator: [51, 230, 133, 164, 1, 127, 131, 173]
        const instructionData = Buffer.alloc(24);
        Buffer.from([51, 230, 133, 164, 1, 127, 131, 173]).copy(instructionData, 0);
        instructionData.writeBigUInt64LE(tokensToSell, 8);
        instructionData.writeBigUInt64LE(minSolOutput, 16);

        transaction.add(new TransactionInstruction({
          programId: PUMP_PROGRAM_ID,
          keys: [
            { pubkey: GLOBAL_CONFIG, isSigner: false, isWritable: false },
            { pubkey: FEE_RECIPIENT, isSigner: false, isWritable: true },
            { pubkey: mintPubkey, isSigner: false, isWritable: false },
            { pubkey: bondingCurve, isSigner: false, isWritable: true },
            { pubkey: associatedBondingCurve, isSigner: false, isWritable: true },
            { pubkey: associatedUser, isSigner: false, isWritable: true },
            { pubkey: this.keypair!.publicKey, isSigner: true, isWritable: true },
            { pubkey: SYSTEM_PROGRAM_ID, isSigner: false, isWritable: false },
            { pubkey: ASSOCIATED_TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
            { pubkey: tokenProgramId, isSigner: false, isWritable: false },
            { pubkey: EVENT_AUTHORITY, isSigner: false, isWritable: false },
            { pubkey: PUMP_PROGRAM_ID, isSigner: false, isWritable: false },
          ],
          data: instructionData,
        }));

        const { blockhash } = await connection.getLatestBlockhash('confirmed');
        transaction.recentBlockhash = blockhash;
        transaction.feePayer = this.keypair!.publicKey;
        transaction.sign(this.keypair!);

        const signature = await connection.sendRawTransaction(transaction.serialize(), { skipPreflight: true });
        console.log(`AGT-06: [PUMP-SELL] ✅ Broadcast: ${signature}`);

        const realised_pnl_sol = (exitPriceSol - position.entry_price_sol) * (position.tokens_received * portion);

        const envelope = createEnvelope('AGT-06', eventType, {
          position_id: position.position_id,
          mint: position.mint,
          sell_portion: portion,
          exit_price: exitPriceSol,
          realised_pnl_sol: realised_pnl_sol,
          tx_signature: signature,
        });

        await updatePosition.run({
          position_id: position.position_id,
          state: 'CLOSED',
          peak_price_sol: position.peak_price_sol,
          exit_price_sol: exitPriceSol,
          exit_tx_signature: signature,
          realised_pnl_sol: realised_pnl_sol,
          updated_at: new Date().toISOString()
        });

        position.state = 'CLOSED';
        this.positions.delete(position.position_id);
        await this.redis.srem('mtus:active_positions', position.position_id);

        await this.redis.publish(eventTypeToChannel(eventType), JSON.stringify(envelope));
        return;
      }

      // ==========================================
      // STANDARD JUPITER PATH (Migrated tokens)
      // ==========================================
      const inputMint = position.mint;
      const outputMint = 'So11111111111111111111111111111111111111112';
      const amount = Math.floor(position.tokens_received * portion * 1e6);
      

      // Helper: Determine which Jupiter API to use based on USD value
      let apiVersion = 'v1';
      try {
        const solPrice = await getSolPriceUsd(this.config);
        const tokenValueUsd = (amount / 1e9) * position.entry_price_sol * solPrice;
        apiVersion = tokenValueUsd >= 6 ? 'v2' : 'v1';
      } catch {
        apiVersion = 'v1'; // Default to v1
      }
      
      // Slippage ladder for v1, RTSE for v2 (no slippageBps)
      let SLIPPAGE_LADDER = [500, 1000, 1500];  // 5%, 10%, 15%
      
      // DUST CLEANUP: If token value is very low (< $0.50), use aggressive slippage to ensure exit
      try {
        const price = await this.fetchPrice(inputMint);
        const solRes = await axios.get(`https://api.jup.ag/price/v3?ids=So11111111111111111111111111111111111111112`);
        const solUsd = solRes.data?.['So11111111111111111111111111111111111111112']?.usdPrice || 150;
        const totalValueUsd = price * (amount / 1e6) * solUsd;
        if (totalValueUsd < 0.5) {
          SLIPPAGE_LADDER = [1500, 2000, 3000]; // Aggressive for dust
          console.log(`AGT-06: [SELL] Low-value position ($${totalValueUsd.toFixed(3)}) — using aggressive slippage ladder`);
        }
      } catch {
        // Non-critical, continue with default slippage
      }

      console.log(`AGT-06: [SELL] Fetching quote for PnL estimation: ${inputMint.slice(0, 8)} → SOL...`);
      
      let quote: QuoteResponse | null = null;
      try {
        const quoteUrl = `https://api.jup.ag/swap/v1/quote?inputMint=${inputMint}&outputMint=${outputMint}&amount=${amount}&slippageBps=500`;
        const res = await fetch(quoteUrl, { headers: { 'x-api-key': process.env.JUPITER_API_KEY || '' } });
        if (res.ok) {
          quote = await res.json() as QuoteResponse;
        }
      } catch (e) {
        console.warn(`AGT-06: [SELL] Quote fetch failed, using fallback for PnL`);
      }
      
      const exitPriceSol = quote && quote.outAmount 
        ? (Number(quote.outAmount) / 1e9) / (position.tokens_received * portion) 
        : position.peak_price_sol;
      console.log(`AGT-06: [${this.isPaperMode() ? 'PAPER' : 'LIVE'}] Exit estimate for ${position.mint}: ${exitPriceSol} SOL`);
      
      if (this.isPaperMode()) {
        const paperTxId = `paper_sell_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        console.log(`AGT-06: [PAPER] Simulated sell ${portion*100}% for ${position.mint}, exit price: ${exitPriceSol} SOL`);
        
        const realised_pnl_sol = (exitPriceSol - position.entry_price_sol) * (position.tokens_received * portion);

        const envelope = createEnvelope('AGT-06', eventType, {
          position_id: position.position_id,
          mint: position.mint,
          sell_portion: portion,
          exit_price: exitPriceSol,
          current_price: position.peak_price_sol,
          realised_pnl_sol: realised_pnl_sol,
          tx_signature: paperTxId,
          isPaper: true,
        });

        await updatePosition.run({
          position_id: position.position_id,
          state: 'CLOSED',
          peak_price_sol: position.peak_price_sol,
          exit_price_sol: exitPriceSol,
          exit_tx_signature: paperTxId,
          realised_pnl_sol: realised_pnl_sol,
          updated_at: new Date().toISOString()
        });

        // ✅ Evict from monitoring map so it is never retried
        position.state = 'CLOSED';
        this.positions.delete(position.position_id);
        await this.redis.srem('mtus:active_positions', position.position_id);

        await this.redis.publish(eventTypeToChannel(eventType), JSON.stringify(envelope));
        return;
      }

      if (!this.keypair) throw new Error('Wallet not loaded');

      // CLI Integration Branch for Sells
      console.log(`AGT-06: [CLI-MODE] Initializing sell via Jupiter CLI binary...`);
      try {
        const txId = await this.executeViaCli(inputMint, 'So11111111111111111111111111111111111111112', amount);
        
        if (txId) {
          console.log(`AGT-06: ${eventType} for ${position.mint} (CLI SUCCESS), tx: ${txId}`);
          
          const realised_pnl_sol = (exitPriceSol - position.entry_price_sol) * (position.tokens_received * portion);
          
          const envelope = createEnvelope('AGT-06', eventType, {
            position_id: position.position_id,
            mint: position.mint,
            sell_portion: portion,
            current_price: position.peak_price_sol,
            realised_pnl_sol: realised_pnl_sol,
            tx_signature: txId,
          });
          
          await updatePosition.run({
            position_id: position.position_id,
            state: 'CLOSED',
            peak_price_sol: position.peak_price_sol,
            exit_price_sol: exitPriceSol,
            exit_tx_signature: txId,
            realised_pnl_sol: realised_pnl_sol,
            updated_at: new Date().toISOString()
          });

          // ✅ Evict from monitoring map so it is never retried
          position.state = 'CLOSED';
          this.positions.delete(position.position_id);
          await this.redis.srem('mtus:active_positions', position.position_id);

          await this.redis.publish(eventTypeToChannel(eventType), JSON.stringify(envelope));

          // POST-SELL BALANCE CHECK — ensure sufficient funds for next trade
          try {
            const connection = new Connection(process.env.HELIUS_RPC_URL!);
            const postSellBalance = await connection.getBalance(this.keypair.publicKey);
            const postSellSol = postSellBalance / 1e9;
            const positionSol = this.config?.trading?.position_size_sol || 0.005;
            const priorityFeeSol = this.config?.trading?.priority_fee_sol || 0.005;
            const ataRentSol = 0.00204;
            const nextTradeCost = positionSol + priorityFeeSol + ataRentSol;
            const canAfford = postSellSol >= nextTradeCost;
            console.log(`AGT-06: [POST-SELL] Wallet balance: ${postSellSol.toFixed(6)} SOL`);
            console.log(`AGT-06: [POST-SELL] Next trade needs: ${nextTradeCost.toFixed(6)} SOL (${positionSol} trade + ${priorityFeeSol} fee + ${ataRentSol} rent)`);
            console.log(`AGT-06: [POST-SELL] ${canAfford ? '✅ Sufficient funds for next trade' : '⚠️ LOW BALANCE — top up wallet before next trade'}`);
          } catch (balErr: any) {
            console.warn(`AGT-06: [POST-SELL] Balance check failed: ${balErr.message}`);
          }

          return;
        }
      } catch (cliErr: any) {
        // CLI failed (e.g. zero balance, network error) — mark FAILED and evict so we never retry
        console.error(`AGT-06: [CLI-FAIL] CLI sell failed for ${position.mint.slice(0,8)}: ${cliErr.message}`);
        position.state = 'FAILED';
        this.positions.delete(position.position_id);
        await this.redis.srem('mtus:active_positions', position.position_id);
        await updatePosition.run({
          position_id: position.position_id,
          state: 'FAILED',
          peak_price_sol: position.peak_price_sol,
          exit_price_sol: null,
          exit_tx_signature: null,
          realised_pnl_sol: null,
          updated_at: new Date().toISOString()
        });
        return; // Do NOT re-throw — just evict and move on
      }
    } catch (error: any) {
      // Outer guard — evict position to prevent infinite retry
      console.log(`AGT-06: [SELL-ERROR] Unexpected sell error for ${position.mint.slice(0,8)}: ${error instanceof Error ? error.message : JSON.stringify(error)}`);
      position.state = 'FAILED';
      this.positions.delete(position.position_id);
      await this.redis.srem('mtus:active_positions', position.position_id);
    }
  }

  async recoverPositions(): Promise<void> {
    try {
      const openPositions = await getOpenPositions.run();
      if (!openPositions || openPositions.length === 0) {
        console.log('AGT-06: No open positions found in DB to recover.');
        return;
      }
      
      console.log(`AGT-06: Recovering ${openPositions.length} positions from DB...`);
      for (const p of openPositions) {
        const position: Position = {
          position_id: p.position_id,
          mint: p.mint,
          entry_price_sol: p.entry_price_sol || 0.001,
          entry_timestamp_utc: p.entry_timestamp_utc || new Date().toISOString(),
          tokens_received: p.tokens_received || 0,
          state: p.state as PositionState,
          tp1_price: p.tp1_price || 0.002,
          tp2_price: p.tp2_price || 0.005,
          sl_price: p.sl_price || 0.0007,
          peak_price_sol: p.peak_price_sol || p.entry_price_sol || 0.001,
          price_buffer: [p.peak_price_sol || 0.001],
        };
        this.positions.set(p.position_id, position);
        console.log(`AGT-06: Recovered position ${p.mint.slice(0, 8)} (${p.position_id})`);
      }
      console.log(`AGT-06: Total positions recovered: ${this.positions.size}`);
    } catch (e: any) {
      console.log(`AGT-06: Recovery error: ${e.message}`);
    }
  }

  async handlePositionOpened(envelopeJson: string): Promise<void> {
    try {
      const envelope: AgentMessageEnvelope = JSON.parse(envelopeJson);
      if (!envelope || !envelope.payload) return;

      const { mint, entry_price_sol, tokens_received, position_id } = envelope.payload;
      
      const entryPriceSol = entry_price_sol ?? envelope.payload.entryPriceSol ?? 0;
      const tokensReceived = tokens_received ?? envelope.payload.tokensReceived ?? 0;
      const positionId = position_id ?? envelope.payload.positionId ?? envelope.correlation_id;

      if (!mint || !positionId) {
        console.error('AGT-06: Missing required fields in position_opened payload');
        return;
      }

      const position: Position = {
        position_id: positionId,
        mint,
        entry_price_sol: entryPriceSol,
        entry_timestamp_utc: envelope.payload.entry_timestamp_utc || new Date().toISOString(),
        tokens_received: tokensReceived,
        state: 'OPEN',
        tp1_price: entryPriceSol * (this.config.trading?.tp1_multiplier || 2.0),
        tp2_price: entryPriceSol * (this.config.trading?.tp2_multiplier || 5.0),
        sl_price: entryPriceSol * (this.config.trading?.sl_multiplier || 0.8),
        peak_price_sol: entryPriceSol,
        price_buffer: [],
      };

      this.positions.set(positionId, position);
      console.log(`AGT-06: Monitoring new position: ${mint} at ${entryPriceSol} SOL`);
      
      // Auto-save to DB to keep in sync
      await insertPosition.run({
        ...position,
        entry_amount_sol: envelope.payload.position_size_sol || 0,
        entry_tx_signature: envelope.payload.tx_signature || '',
        entry_timestamp_utc: position.entry_timestamp_utc,
        updated_at: new Date().toISOString()
      });
    } catch (e: any) {
      console.error(`AGT-06: Error handling position opened message: ${e.message}`);
    }
  }

  async monitorPositions(): Promise<void> {
    if (this.positions.size === 0) {
      await this.recoverPositions();
    }

    // Identify active positions to batch their price lookups
    const activePositions = Array.from(this.positions.entries()).filter(
      ([_, p]) => p.state !== 'CLOSED' && p.state !== 'FAILED'
    );
    
    // Clean up closed/failed positions from map
    for (const [id, position] of this.positions) {
       if (position.state === 'CLOSED' || position.state === 'FAILED') {
         this.positions.delete(id);
         await this.redis.srem('mtus:active_positions', id);
       }
    }

    if (activePositions.length === 0) return;

    // Fetch all prices in one single bulk request
    const mintsToFetch = activePositions.map(([_, p]) => p.mint);
    const batchPrices = await this.fetchPricesBatch(mintsToFetch);

    // Process each active position
    for (const [id, position] of activePositions) {
      const price = batchPrices[position.mint] || 0;
      await this.updatePositionState(position, price);
      
      if (price > 0) {
        const entryPrice = position.entry_price_sol || 0.001;
        const pnlPct = ((price - entryPrice) / entryPrice) * 100;
        console.log(`AGT-06: [MONITOR] ${position.mint.slice(0, 8)} | Price: ${price.toFixed(9)} SOL | PnL: ${pnlPct.toFixed(2)}% | State: ${position.state} | Batch Size: ${mintsToFetch.length}`);
        
        // Update peak price in DB if it increased
        if (price > (position.peak_price_sol || 0)) {
          await updatePosition.run({
            position_id: position.position_id,
            state: position.state,
            peak_price_sol: price,
            updated_at: new Date().toISOString()
          });
        }
      }
    }
  }

  async run(): Promise<void> {
    console.log(`AGT-06: [STARTING] Sentinel v${VERSION}`);
    this.running = true;
    
    // Subscriber setup
    let subscriber: Redis | null = null;
    let isSubscribed = false;

    const setupSubscription = async () => {
      if (isSubscribed) return;
      subscriber = this.redis.duplicate();
      await subscriber.subscribe(CHANNEL_POSITION_OPENED);
      subscriber.on('message', (channel: string, message: string) => {
        try {
          if (channel === CHANNEL_POSITION_OPENED && message) {
            this.handlePositionOpened(message);
          }
        } catch (err: any) {
          console.error(`AGT-06: Error in subscriber message: ${err.message}`);
        }
      });
      isSubscribed = true;
      console.log('AGT-06: Subscribed to position_opened channel');
    };

    const tearDownSubscription = async () => {
      if (!isSubscribed || !subscriber) return;
      await subscriber.unsubscribe();
      await subscriber.quit();
      subscriber = null;
      isSubscribed = false;
      console.log('AGT-06: Unsubscribed from position_opened channel');
    };

    // Wait 3 seconds for DB to initialize before first recovery attempt
    console.log('AGT-06: Waiting for DB initialization...');
    await new Promise(r => setTimeout(r, 3000));

    // Price polling loop
    while (this.running) {
      try {
        const active = isOperationalWindowActive();

        if (active && !isSubscribed) {
          await setupSubscription();
        } else if (!active && isSubscribed) {
          await tearDownSubscription();
        }

        if (!active) {
          await new Promise(r => setTimeout(r, 60000));
          continue;
        }

        await this.monitorPositions();
      } catch (loopErr: any) {
        console.log(`AGT-06: [LOOP ERROR] ${loopErr.message}`);
      }
      await new Promise(r => setTimeout(r, POLLING_INTERVAL_MS));
    }
  }

  private async executeViaCli(fromMint: string, toMint: string, amountRaw: number): Promise<string> {
    try {
      console.log(`AGT-06: [CLI-SELL] Executing (RTSE AUTO-SLIPPAGE): ${fromMint.slice(0, 8)} → ${toMint.slice(0, 8)}... (${amountRaw} raw)`);
      
      const cmd = `jup spot swap --from ${fromMint} --to ${toMint} --raw-amount ${amountRaw} --key sniper -f json`;
      const output = execSync(cmd).toString();
      const result = JSON.parse(output);
      
      if (result.error) {
        throw new Error(result.error);
      }
      
      return result.signature || result.txid || '';
    } catch (e: any) {
      console.error(`AGT-06: [CLI-ERROR] CLI swap failed: ${e.message}`);
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
}


