import * as fs from 'fs';
import * as yaml from 'js-yaml';
import * as path from 'path';
import { Connection, PublicKey, Transaction, VersionedTransaction, Keypair } from '@solana/web3.js';
import { loadKeypairFromKeystore } from '../shared/keystore';
import { QuoteResponse } from '@jup-ag/api';
import { createEnvelope, AgentMessageEnvelope, EventType } from '../shared/envelope';
import { CHANNEL_POSITION_OPENED, eventTypeToChannel } from '../shared/channels';
import Redis from 'ioredis';
import { createRedisClient } from '../shared/redis';
import dotenv from 'dotenv';
import axios from 'axios';
import { getOpenPositions, updatePosition, insertAuditLog } from '../shared/db';
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

  constructor(config?: any) {
    if (config) {
      this.config = config;
    } else {
      this.loadConfig();
    }
  }

  /**
   * Initialize resources like Redis
   */
  async init(redis?: Redis): Promise<void> {
    this.redis = redis || await createRedisClient();
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

  async fetchPrice(mint: string): Promise<number> {
    try {
      const solUsd = await getSolPriceUsd(this.config);
      const data: any = await rateLimitedRequest(async (baseUrl) => {
        const resp = await axios.get(`${baseUrl}/price/v2?ids=${mint}`, { timeout: 3000 });
        return resp.data;
      }, this.config);
      
      const tokenUsd = data?.data?.[mint]?.price || 0;
      if (tokenUsd > 0) return tokenUsd / solUsd;
      throw new Error("Jupiter returned 0");
    } catch {
      // Fallback: Birdeye (returns USD, so we must divide by SOL price)
      try {
        const [tokenResp, solResp] = await Promise.all([
          axios.get(`https://public-api.birdeye.so/public/price?address=${mint}`, {
            headers: { 'X-API-KEY': BIRDEYE_API_KEY },
            timeout: 3000,
          }),
          axios.get(`https://api.jup.ag/price/v3?ids=So11111111111111111111111111111111111111112`, { timeout: 3000 })
        ]);
        const tokenUsd = tokenResp.data?.data?.value || 0;
        const solUsd = solResp.data?.['So11111111111111111111111111111111111111112']?.usdPrice || 150;
        return tokenUsd / solUsd;
      } catch {
        return 0;
      }
    }
  }

  async updatePositionState(position: Position, currentPrice: number): Promise<void> {
    position.price_buffer.push(currentPrice);
    if (position.price_buffer.length > PRICE_BUFFER_SIZE) position.price_buffer.shift();

    // Time-based stop loss (Configurable, default 30m)
    const entryTime = new Date(position.entry_timestamp_utc).getTime();
    const now = Date.now();
    const timeSlHours = this.config?.trading?.time_sl_hours || 0.5;
    if (timeSlHours > 0) {
      const timeSlMs = timeSlHours * 60 * 60 * 1000;
      if (position.state === 'OPEN' && (now - entryTime) > timeSlMs) {
        console.log(`AGT-06: [TIME STOP] Position ${position.position_id} hit ${timeSlHours}h limit. Closing.`);
        position.state = 'STOP_LOSS';
        await this.sellPortion(position, 1.0, 'time_sl_hit');
        return;
      }
    }

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
        position.state = 'TAKE_PROFIT_1';
        await this.sellPortion(position, 0.5, 'tp1_hit');
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
          const envelope = createEnvelope('AGT-06', eventType, {
            position_id: position.position_id,
            mint: position.mint,
            sell_portion: portion,
            exit_price: position.peak_price_sol, // Mock price
            tx_signature: `paper_pump_sell_${Date.now()}`,
            isPaper: true,
          });
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
        const vTokenReserves = BigInt(pumpReserves.virtual_token_reserves);
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

        const envelope = createEnvelope('AGT-06', eventType, {
          position_id: position.position_id,
          mint: position.mint,
          sell_portion: portion,
          exit_price: Number(expectedSol) / 1e9 / (Number(tokensToSell) / 1e6),
          tx_signature: signature,
        });
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
          console.log(`AGT-06: [DUST-CLEANUP] Token value $${totalValueUsd.toFixed(4)} is very low. Using aggressive slippage ladder.`);
          SLIPPAGE_LADDER = [2500, 5000, 9900]; // 25%, 50%, 99%
        }
      } catch (e) {
        // Fallback to standard ladder if price check fails
      }
      let quote: QuoteResponse | null = null;
      
      if (apiVersion === 'v1') {
        // v1 API: use slippage ladder (retry with higher slippage)
        for (const slippageBps of SLIPPAGE_LADDER) {
          try {
            const q: QuoteResponse = await rateLimitedRequest(async (baseUrl) => {
              const quoteUrl = `${baseUrl}/swap/v1/quote?inputMint=${inputMint}&outputMint=${outputMint}&amount=${amount}&slippageBps=${slippageBps}`;
              const res = await fetch(quoteUrl);
              if (!res.ok) throw new Error(`V1 quote failed: ${res.status}`);
              return res.json() as Promise<QuoteResponse>;
            }, this.config);
            if (q && q.outAmount) {
              quote = q;
              console.log(`AGT-06: [SELL] v1 quote with ${slippageBps/10}% slippage`);
              break;
            }
          } catch {
            // Try next slippage level
          }
        }
      } else {
        // v2 API: use RTSE (no slippageBps to enable auto-slippage)
        try {
          quote = await rateLimitedRequest(async (baseUrl) => {
            const quoteUrl = `${baseUrl}/swap/v2/quote?inputMint=${inputMint}&outputMint=${outputMint}&amount=${amount}`;
            const res = await fetch(quoteUrl);
            if (!res.ok) throw new Error(`V2 quote failed: ${res.status}`);
            return res.json() as Promise<QuoteResponse>;
          }, this.config);
        } catch (e) {
          console.error(`AGT-06: [SELL] V2 quote failed, fallback to V1`);
          apiVersion = 'v1'; // Logic to retry with v1 if needed could go here
        }
      }
      
      console.log(`AGT-06: [SELL] Using ${apiVersion.toUpperCase()} API for sell (portion: ${portion * 100}%)`);
      
      if (!quote || !quote.outAmount) throw new Error('No Jupiter quote for sell');
      
      const exitPriceSol = Number(quote.outAmount) / 1e9;
      console.log(`AGT-06: [${this.isPaperMode() ? 'PAPER' : 'LIVE'}] Exit quote for ${position.mint}: ${exitPriceSol} SOL`);
      
      if (this.isPaperMode()) {
        const paperTxId = `paper_sell_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        console.log(`AGT-06: [PAPER] Simulated sell ${portion*100}% for ${position.mint}, exit price: ${exitPriceSol} SOL`);
        
        const envelope = createEnvelope('AGT-06', eventType, {
          position_id: position.position_id,
          mint: position.mint,
          sell_portion: portion,
          exit_price: exitPriceSol,
          current_price: position.peak_price_sol,
          tx_signature: paperTxId,
          isPaper: true,
        });
        await this.redis.publish(eventTypeToChannel(eventType), JSON.stringify(envelope));
        return;
      }

      if (!this.keypair) throw new Error('Wallet not loaded');

      // Preflight: Check wallet has enough SOL for fees before getting swap transaction
      const HELIUS_RPC_URL = process.env.HELIUS_RPC_URL || 'https://mainnet.helius-rpc.com/?api-key=' + process.env.HELIUS_KEY;
      const connection = new Connection(HELIUS_RPC_URL);
      const walletBalance = await connection.getBalance(this.keypair.publicKey);
      const MIN_BALANCE_FOR_SELL = 500000; // 0.0005 SOL minimum for fees
      if (walletBalance < MIN_BALANCE_FOR_SELL) {
        console.log(`AGT-06: [SELL] ❌ ABORTED: Insufficient SOL for fees. Have: ${walletBalance/1e9} SOL, Need: ${MIN_BALANCE_FOR_SELL/1e9} SOL`);
        const envelope = createEnvelope('AGT-06', 'trade_failed', {
          position_id: position.position_id,
          mint: position.mint,
          sell_portion: portion,
          error: 'Insufficient SOL for sell transaction fees',
          current_price: position.peak_price_sol,
        }, '');
        await this.redis.publish(eventTypeToChannel(eventType), JSON.stringify(envelope));
        return;
      }

      const swapResult: any = await rateLimitedRequest(async (baseUrl) => {
        const swapUrl = `${baseUrl}/swap/${apiVersion}/swap`;
        const swapRes = await fetch(swapUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            quoteResponse: quote,
            userPublicKey: this.keypair!.publicKey.toBase58(),
            wrapUnwrapSOL: true,
            prioritizationFeeLamports: 100000,
            maxPrioritizationFeeLamports: 100000,
          }),
        });
        if (!swapRes.ok) throw new Error(`Swap failed: ${swapRes.status}`);
        return swapRes.json();
      }, this.config);
      const txBytes = Buffer.from(swapResult.swapTransaction, 'base64');

      let signedTxBytes: Uint8Array;
      
      try {
        const versionedTx = VersionedTransaction.deserialize(txBytes);
        versionedTx.sign([this.keypair!]);
        signedTxBytes = versionedTx.serialize();
      } catch (e) {
        // Fallback to legacy
        const legacyTx = Transaction.from(txBytes);
        legacyTx.sign(this.keypair!);
        signedTxBytes = legacyTx.serialize();
      }

      this.keypair!.secretKey.fill(0);

      const txId = await connection.sendRawTransaction(signedTxBytes);
      await connection.confirmTransaction(txId);

      console.log(`AGT-06: ${eventType} for ${position.mint}, sold ${portion*100}%, tx: ${txId}`);

      const realised_pnl_sol = (position.peak_price_sol - position.entry_price_sol) * (position.tokens_received * portion);
      
      const envelope = createEnvelope('AGT-06', eventType, {
        position_id: position.position_id,
        mint: position.mint,
        sell_portion: portion,
        current_price: position.peak_price_sol,
        realised_pnl_sol: realised_pnl_sol,
        tx_signature: txId,
      });
      
      // Update DB with final state and PnL
      updatePosition.run({
        position_id: position.position_id,
        state: position.state,
        peak_price_sol: position.peak_price_sol,
        exit_price_sol: position.peak_price_sol,
        exit_tx_signature: txId,
        realised_pnl_sol: realised_pnl_sol,
        updated_at: new Date().toISOString()
      });
      await this.redis.publish(eventTypeToChannel(eventType), JSON.stringify(envelope));
    } catch (error) {
      console.log(`AGT-06: Sell failed: ${error instanceof Error ? error.message : JSON.stringify(error)}`);
    }
  }

  async recoverPositions(): Promise<void> {
    try {
      const openPositions = getOpenPositions.run();
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
      const { mint, entryPriceSol, tokensReceived, position_id } = envelope.payload;
      const position: Position = {
        position_id,
        mint,
        entry_price_sol: entryPriceSol,
        entry_timestamp_utc: new Date().toISOString(),
        tokens_received: tokensReceived,
        state: 'OPEN',
        tp1_price: entryPriceSol * (this.config.trading?.tp1_multiplier || 2.0),
        tp2_price: entryPriceSol * (this.config.trading?.tp2_multiplier || 5.0),
        sl_price: entryPriceSol * (this.config.trading?.sl_multiplier || 0.8),
        peak_price_sol: entryPriceSol,
        price_buffer: [],
      };

      this.positions.set(position_id, position);
      console.log(`AGT-06: Monitoring new position: ${mint} at ${entryPriceSol} SOL`);
      
      // Auto-save to DB if needed
      // insertPosition.run(position);
    } catch (e: any) {
      console.error(`AGT-06: Error handling position opened message: ${e.message}`);
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

        if (this.positions.size === 0) {
          // Periodic check for DB recovery if empty
          await this.recoverPositions();
        }

        for (const [id, position] of this.positions) {
          if (position.state === 'CLOSED' || position.state === 'FAILED') continue;
          
          const price = await this.fetchPrice(position.mint);
          if (price > 0) {
            const entryPrice = position.entry_price_sol || 0.001;
            const pnlPct = ((price - entryPrice) / entryPrice) * 100;
            console.log(`AGT-06: [MONITOR] ${position.mint.slice(0, 8)} | Price: ${price.toFixed(9)} SOL | PnL: ${pnlPct.toFixed(2)}% | State: ${position.state}`);
            
            await this.updatePositionState(position, price);
            
            // Update peak price in DB if it increased
            if (price > (position.peak_price_sol || 0)) {
              updatePosition.run({
                position_id: position.position_id,
                state: position.state,
                peak_price_sol: price,
                updated_at: new Date().toISOString()
              });
            }
          }
        }
      } catch (loopErr: any) {
        console.log(`AGT-06: [LOOP ERROR] ${loopErr.message}`);
      }
      await new Promise(r => setTimeout(r, POLLING_INTERVAL_MS));
    }
  }

  async stop(): Promise<void> {
    this.running = false;
    await this.redis.quit();
  }
}


