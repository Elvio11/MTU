import * as fs from 'fs';
import * as yaml from 'js-yaml';
import * as path from 'path';
import { Connection, PublicKey, Transaction, VersionedTransaction, Keypair } from '@solana/web3.js';
import { loadKeypairFromKeystore } from '../shared/keystore';
import { QuoteResponse } from '@jup-ag/api';
import { createEnvelope, AgentMessageEnvelope, EventType } from '../shared/envelope';
import { CHANNEL_POSITION_OPENED, eventTypeToChannel } from '../shared/channels';
import Redis from 'ioredis';
import dotenv from 'dotenv';
import axios from 'axios';
import { getOpenPositions, updatePosition, insertAuditLog } from '../shared/db';

dotenv.config();

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

const IS_PAPER_MODE = (process.env.MTUS_ENVIRONMENT || 'paper').toLowerCase() === 'paper';

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
  private redis: Redis;
  private positions: Map<string, Position> = new Map();
  private running: boolean = false;
  private keypair: any;
  private config: any;

  constructor() {
    this.loadConfig();
    this.redis = new Redis(REDIS_URL);
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
      // Primary: Jupiter v3 price API (returns usdPrice)
      const [tokenResp, solResp] = await Promise.all([
        axios.get(`https://api.jup.ag/price/v3?ids=${mint}`, { timeout: 3000 }),
        axios.get(`https://api.jup.ag/price/v3?ids=So11111111111111111111111111111111111111112`, { timeout: 3000 })
      ]);
      const tokenUsd = tokenResp.data?.[mint]?.usdPrice || 0;
      const solUsd = solResp.data?.['So11111111111111111111111111111111111111112']?.usdPrice || 150;
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

  updatePositionState(position: Position, currentPrice: number): void {
    position.price_buffer.push(currentPrice);
    if (position.price_buffer.length > PRICE_BUFFER_SIZE) position.price_buffer.shift();

    // Time-based stop loss (Configurable, default 30m)
    const entryTime = new Date(position.entry_timestamp_utc).getTime();
    const now = Date.now();
    const timeSlHours = this.config?.trading?.time_sl_hours || 0.5;
    const timeSlMs = timeSlHours * 60 * 60 * 1000;

    if (position.state === 'OPEN' && (now - entryTime) > timeSlMs) {
      console.log(`AGT-06: [TIME STOP] Position ${position.position_id} hit ${timeSlHours}h limit. Closing.`);
      position.state = 'STOP_LOSS';
      this.sellPortion(position, 1.0, 'time_sl_hit');
      return;
    }

    if (position.state === 'OPEN') {
      if (currentPrice >= position.tp1_price) {
        position.state = 'TAKE_PROFIT_1';
        this.sellPortion(position, 0.5, 'tp1_hit');
      } else if (currentPrice <= position.sl_price) {
        position.state = 'STOP_LOSS';
        this.sellPortion(position, 1.0, 'stop_loss_hit');
      }
    } else if (position.state === 'TAKE_PROFIT_1') {
      if (currentPrice > position.peak_price_sol) position.peak_price_sol = currentPrice;
      const trailingPrice = position.peak_price_sol * (1 - (this.config?.trading?.trailing_stop_pct || 15) / 100);
      if (currentPrice <= trailingPrice) {
        position.state = 'CLOSED';
        this.sellPortion(position, 0.5, 'trailing_stop_hit');
      } else if (currentPrice >= position.tp2_price) {
        position.state = 'CLOSED';
        this.sellPortion(position, 0.5, 'tp2_hit');
      }
    } else if (position.state === 'TRAILING') {
      if (currentPrice > position.peak_price_sol) position.peak_price_sol = currentPrice;
      const trailingPrice = position.peak_price_sol * (1 - (this.config?.trading?.trailing_stop_pct || 15) / 100);
      if (currentPrice >= position.tp2_price) {
        // TRAILING → CLOSED
        position.state = 'CLOSED';
        this.sellPortion(position, 0.5, 'tp2_hit');
      } else if (currentPrice <= trailingPrice) {
        position.state = 'CLOSED';
        this.sellPortion(position, 0.5, 'trailing_stop_hit');
      }
    } else if (position.state === 'TAKE_PROFIT_2') {
      // Should not be reachable now, but just in case
      position.state = 'CLOSED';
    }
  }

  async sellPortion(position: Position, portion: number, eventType: EventType): Promise<void> {
    try {
      const inputMint = position.mint;
      const outputMint = 'So11111111111111111111111111111111111111112';
      const amount = Math.floor(position.tokens_received * portion * 1e6);
      
      // Get SOL price for API version selection
      let apiVersion = 'v1';
      try {
        const priceRes = await fetch('https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112', { signal: AbortSignal.timeout(5000) });
        const priceData: any = await priceRes.json();
        const solPrice = priceData?.data?.So11111111111111111111111111111111111111112?.price || 200;
        const tokenValueUsd = (amount / 1e9) * position.entry_price_sol * solPrice;
        apiVersion = tokenValueUsd >= 6 ? 'v2' : 'v1';
      } catch {
        apiVersion = 'v1'; // Default to v1
      }
      
      // Slippage ladder for v1, RTSE for v2 (no slippageBps)
      const SLIPPAGE_LADDER = [500, 1000, 1500];  // 5%, 10%, 15%
      let quote: QuoteResponse | null = null;
      
      if (apiVersion === 'v1') {
        // v1 API: use slippage ladder (retry with higher slippage)
        for (const slippageBps of SLIPPAGE_LADDER) {
          const quoteUrl = `https://api.jup.ag/swap/v1/quote?inputMint=${inputMint}&outputMint=${outputMint}&amount=${amount}&slippageBps=${slippageBps}`;
          try {
            const quoteRes = await fetch(quoteUrl);
            const q = await quoteRes.json() as QuoteResponse;
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
        const quoteUrl = `https://api.jup.ag/swap/v2/quote?inputMint=${inputMint}&outputMint=${outputMint}&amount=${amount}`;
        const quoteRes = await fetch(quoteUrl);
        quote = await quoteRes.json() as QuoteResponse;
      }
      
      console.log(`AGT-06: [SELL] Using ${apiVersion.toUpperCase()} API for sell (portion: ${portion * 100}%)`);
      
      if (!quote || !quote.outAmount) throw new Error('No Jupiter quote for sell');
      
      if (!quote || !quote.outAmount) throw new Error('No Jupiter quote for sell');
      
      const exitPriceSol = Number(quote.outAmount) / 1e9;
      console.log(`AGT-06: [${IS_PAPER_MODE ? 'PAPER' : 'LIVE'}] Exit quote for ${position.mint}: ${exitPriceSol} SOL`);
      
      if (IS_PAPER_MODE) {
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

      const swapUrl = `https://api.jup.ag/swap/${apiVersion}/swap`;
      const swapRes = await fetch(swapUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quoteResponse: quote,
          userPublicKey: this.keypair!.publicKey.toBase58(),
          wrapUnwrapSOL: true,  // Enable to recover ATA rent (~0.00244 SOL) when selling 100%
          prioritizationFeeLamports: 100000,
          maxPrioritizationFeeLamports: 100000,  // Cap at 0.001 SOL
        }),
      });
      const swapResult = await swapRes.json() as { swapTransaction: string };
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

      const envelope = createEnvelope('AGT-06', eventType, {
        position_id: position.position_id,
        mint: position.mint,
        sell_portion: portion,
        current_price: position.peak_price_sol,
        tx_signature: txId,
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
    const envelope: AgentMessageEnvelope = JSON.parse(envelopeJson);
    const { mint, entryPriceSol, tokensReceived, position_id } = envelope.payload;
    const position: Position = {
      position_id,
      mint,
      entry_price_sol: entryPriceSol,
      entry_timestamp_utc: new Date().toISOString(),
      tokens_received: tokensReceived,
      state: 'OPEN',
      tp1_price: entryPriceSol * (this.config?.trading?.tp1_multiplier || 2.0),
      tp2_price: entryPriceSol * (this.config?.trading?.tp2_multiplier || 5.0),
      sl_price: entryPriceSol * (this.config?.trading?.sl_multiplier || 0.7),
      peak_price_sol: entryPriceSol,
      price_buffer: [entryPriceSol],
    };
    this.positions.set(position_id, position);
    console.log(`AGT-06: New position opened for ${mint}`);
  }

  async run(): Promise<void> {
    console.log(`AGT-06: [STARTING] Sentinel v${VERSION}`);
    this.running = true;
    
    try {
      const subscriber = this.redis.duplicate();
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
      console.log('AGT-06: Subscribed to position_opened channel');
    } catch (e: any) {
      console.error(`AGT-06: Failed to initialize Redis subscriber: ${e.message}`);
    }

    // Wait 3 seconds for DB to initialize before first recovery attempt
    console.log('AGT-06: Waiting for DB initialization...');
    await new Promise(r => setTimeout(r, 3000));

    // Price polling loop
    while (this.running) {
      try {
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
            
            this.updatePositionState(position, price);
            
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


