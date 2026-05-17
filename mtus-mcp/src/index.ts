import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import dotenv from "dotenv";
import * as argon2 from "argon2";
import * as nacl from "tweetnacl";
import { Connection, PublicKey, Keypair } from "@solana/web3.js";

const BOT_ROOT = "e:/New folder (2)";
const CONFIG_PATH = path.join(BOT_ROOT, "config/config.yaml");

// Load env files securely
dotenv.config({ path: path.resolve(BOT_ROOT, ".env") });

const ARGON2_OPTIONS = {
  type: argon2.argon2id,
  timeCost: 4,
  memoryCost: 65536,
  parallelism: 2,
  hashLength: 32,
  raw: true, // Get raw bytes instead of formatted string
};

// Decrypt keystore to obtain the public key securely
async function getSniperAddress(keystorePath: string, passphrase: string): Promise<string> {
  const keystoreData = JSON.parse(fs.readFileSync(keystorePath, "utf-8"));
  const salt = Buffer.from(keystoreData.salt, "hex");
  const derivedKey = await argon2.hash(passphrase, { ...ARGON2_OPTIONS, salt });
  const key = Buffer.from(derivedKey);
  const nonce = Buffer.from(keystoreData.nonce, "hex");
  const encrypted = Buffer.from(keystoreData.encryptedSecretKey, "hex");
  
  const secretKey = nacl.secretbox.open(encrypted, nonce, key);
  if (!secretKey) throw new Error("Invalid passphrase or corrupted keystore");
  
  const keypair = Keypair.fromSecretKey(new Uint8Array(secretKey));
  return keypair.publicKey.toBase58();
}

const server = new Server(
  {
    name: "mtus-control",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "get_system_status",
        description: "Get real-time health, wallet balances, and PM2 status of the MTUS bot.",
        inputSchema: { type: "object", properties: {} },
      },
      {
        name: "update_trading_config",
        description: "Update trading parameters like position size, TP, or SL in config.yaml.",
        inputSchema: {
          type: "object",
          properties: {
            positionSizeSOL: { type: "number" },
            tp1_multiplier: { type: "number" },
            tp2_multiplier: { type: "number" },
            sl_multiplier: { type: "number" },
            priorityFeeSOL: { type: "number" },
          },
        },
      },
      {
        name: "get_performance_report",
        description: "Fetch win rate, total profit, and recent trade history from the database.",
        inputSchema: {
          type: "object",
          properties: {
            limit: { type: "number", default: 10 },
          },
        },
      },
      {
        name: "trigger_maintenance",
        description: "Manually trigger ATA rent reclamation and wallet rebalancing.",
        inputSchema: { type: "object", properties: {} },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "get_system_status": {
        // Safe PM2 Status resolution
        let pm2Data: any[] = [];
        try {
          const pm2Status = execSync("pm2 jlist").toString();
          pm2Data = JSON.parse(pm2Status).map((p: any) => ({
            name: p.name,
            status: p.pm2_env?.status,
            cpu: p.monit?.cpu,
            mem: p.monit?.memory,
          }));
        } catch (err: any) {
          pm2Data = [{ error: "PM2 is not active or not installed in current context: " + err.message }];
        }

        // Safe Configuration loading
        const config = yaml.load(fs.readFileSync(CONFIG_PATH, "utf8")) as any;

        // Resolve RPC URL securely
        let rpcUrl = process.env.HELIUS_RPC_URL || process.env.QUICKNODE_URL;
        if (!rpcUrl && config.rpc?.providers?.length > 0) {
          const provider = config.rpc.providers.find((p: any) => p.priority === 1) || config.rpc.providers[0];
          let rawUrl = provider.http_url;
          if (rawUrl) {
            rpcUrl = rawUrl.replace(/\${([^}]+)}/g, (_: string, envName: string) => process.env[envName] || "")
                           .replace(/\$([a-zA-Z0-9_]+)/g, (_: string, envName: string) => process.env[envName] || "");
          }
        }
        if (!rpcUrl) {
          rpcUrl = "https://api.mainnet-beta.solana.com";
        }

        // Decrypt keystore for Sniper wallet address
        let sniperAddress = "Unknown";
        const keystorePathRaw = config.wallets?.sniper_keystore_path || "./keystores/sniper.keystore";
        const keystorePath = path.isAbsolute(keystorePathRaw) ? keystorePathRaw : path.resolve(BOT_ROOT, keystorePathRaw);
        const passphrase = process.env.SNIPER_PASSPHRASE;

        if (fs.existsSync(keystorePath) && passphrase) {
          try {
            sniperAddress = await getSniperAddress(keystorePath, passphrase);
          } catch (err: any) {
            console.error(`Keystore decryption failed: ${err.message}`);
          }
        }

        // Query Balance using Solana Connection directly (no subprocess spawn)
        let balanceSol = "0 SOL";
        if (sniperAddress !== "Unknown") {
          try {
            const conn = new Connection(rpcUrl, "confirmed");
            const balanceLamports = await conn.getBalance(new PublicKey(sniperAddress));
            balanceSol = (balanceLamports / 1e9).toFixed(4) + " SOL";
          } catch (err: any) {
            balanceSol = "Error: " + err.message;
          }
        } else {
          balanceSol = "Keystore decryption unavailable (passphrase or file missing)";
        }

        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              pm2: pm2Data,
              sniper_address: sniperAddress,
              sniper_balance: balanceSol,
              rpc_url: rpcUrl,
              config_active: {
                position_size: config.trading?.position_size_sol,
                risk: {
                  tp1_multiplier: config.trading?.tp1_multiplier,
                  tp2_multiplier: config.trading?.tp2_multiplier,
                  sl_multiplier: config.trading?.sl_multiplier,
                  priority_fee_sol: config.trading?.priority_fee_sol
                }
              }
            }, null, 2)
          }]
        };
      }

      case "update_trading_config": {
        const config = yaml.load(fs.readFileSync(CONFIG_PATH, "utf8")) as any;
        if (args?.positionSizeSOL !== undefined) config.trading.position_size_sol = args.positionSizeSOL;
        if (args?.tp1_multiplier !== undefined) config.trading.tp1_multiplier = args.tp1_multiplier;
        if (args?.tp2_multiplier !== undefined) config.trading.tp2_multiplier = args.tp2_multiplier;
        if (args?.sl_multiplier !== undefined) config.trading.sl_multiplier = args.sl_multiplier;
        if (args?.priorityFeeSOL !== undefined) config.trading.priority_fee_sol = args.priorityFeeSOL;
        
        fs.writeFileSync(CONFIG_PATH, yaml.dump(config));
        
        // Safely attempt restarting the bot under PM2
        let pm2RestartResult = "Restart skipped (PM2 not running)";
        try {
          execSync("pm2 restart all");
          pm2RestartResult = "Agents restarted successfully under PM2.";
        } catch (err: any) {
          pm2RestartResult = `Restart skipped or failed: ${err.message}`;
        }
        
        return {
          content: [{ type: "text", text: `Configuration updated. ${pm2RestartResult}` }]
        };
      }

      case "get_performance_report": {
        // Query PostgreSQL directly using node-postgres
        const { Pool } = await import("pg");
        const pool = new Pool({
          connectionString: process.env.DATABASE_URL ||
            `postgresql://${process.env.DB_USER || "postgres"}:${process.env.DB_PASSWORD || "postgres"}@${process.env.DB_HOST || "localhost"}:${process.env.DB_PORT || "5432"}/${process.env.DB_NAME || "mtus_db"}`,
        });

        const limit = (args?.limit as number) || 10;
        const [stateStats, recentTrades] = await Promise.all([
          pool.query(`SELECT state, COUNT(*) AS count FROM positions GROUP BY state ORDER BY count DESC`),
          pool.query(
            `SELECT position_id, mint, state, entry_price_sol, realised_pnl_sol, updated_at
             FROM positions ORDER BY updated_at DESC LIMIT $1`,
            [limit]
          ),
        ]);

        const wins = stateStats.rows.find((r: any) => r.state === "CLOSED" && r.count > 0);
        const closed = stateStats.rows.find((r: any) => r.state === "CLOSED");
        const pnlResult = await pool.query(`SELECT SUM(realised_pnl_sol) AS total FROM positions WHERE state = 'CLOSED'`);

        await pool.end();

        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              state_summary: stateStats.rows,
              total_profit_sol: pnlResult.rows[0]?.total ?? 0,
              recent_trades: recentTrades.rows,
            }, null, 2)
          }]
        };
      }

      case "trigger_maintenance": {
        let output = "";
        try {
          output = execSync(`cd "${BOT_ROOT}" && node burn_and_close_ata.js`).toString();
        } catch (err: any) {
          output = `Maintenance script execution failed: ${err.message}\n${err.stderr?.toString() || ""}`;
        }
        return {
          content: [{ type: "text", text: `Maintenance output:\n${output}` }]
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    return {
      content: [{ type: "text", text: `Error executing tool ${name}: ${error.message}` }],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});

