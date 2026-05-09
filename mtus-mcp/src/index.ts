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

const BOT_ROOT = "e:/New folder (2)";
const CONFIG_PATH = path.join(BOT_ROOT, "config/config.yaml");

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
        const pm2Status = execSync("pm2 jlist").toString();
        const config = yaml.load(fs.readFileSync(CONFIG_PATH, "utf8")) as any;
        
        // Use a small helper script or command to get balances
        const sniperBalance = execSync(`node -e "const { Connection, PublicKey } = require('@solana/web3.js'); (async () => { const conn = new Connection('${config.rpc_endpoints.primary}'); console.log(await conn.getBalance(new PublicKey('${config.wallets.sniper_address}'))); })()"`).toString().trim();

        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              pm2: JSON.parse(pm2Status).map((p: any) => ({ name: p.name, status: p.pm2_env.status, cpu: p.monit.cpu, mem: p.monit.memory })),
              sniper_balance: parseInt(sniperBalance) / 1e9 + " SOL",
              config_active: {
                position_size: config.trading.position_size_sol,
                risk: config.trading.risk_management
              }
            }, null, 2)
          }]
        };
      }

      case "update_trading_config": {
        const config = yaml.load(fs.readFileSync(CONFIG_PATH, "utf8")) as any;
        if (args?.positionSizeSOL) config.trading.position_size_sol = args.positionSizeSOL;
        if (args?.tp1_multiplier) config.trading.risk_management.tp1_multiplier = args.tp1_multiplier;
        if (args?.tp2_multiplier) config.trading.risk_management.tp2_multiplier = args.tp2_multiplier;
        if (args?.sl_multiplier) config.trading.risk_management.sl_multiplier = args.sl_multiplier;
        
        fs.writeFileSync(CONFIG_PATH, yaml.dump(config));
        execSync("pm2 restart all"); // Apply changes
        
        return {
          content: [{ type: "text", text: "Configuration updated and agents restarted successfully." }]
        };
      }

      case "get_performance_report": {
        // Query the SQLite database via shell
        const dbPath = path.join(BOT_ROOT, "data/positions.db");
        const query = "SELECT status, count(*) as count FROM positions GROUP BY status";
        const stats = execSync(`sqlite3 "${dbPath}" "${query}"`).toString();
        
        return {
          content: [{ type: "text", text: `Trade Stats:\n${stats}` }]
        };
      }

      case "trigger_maintenance": {
        const output = execSync(`cd "${BOT_ROOT}" && node burn_and_close_ata.js`).toString();
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
