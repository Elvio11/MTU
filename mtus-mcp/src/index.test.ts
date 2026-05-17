// Mock handlers store
const mockHandlers = new Map<any, Function>();

// Mock MCP SDK Server
jest.mock("@modelcontextprotocol/sdk/server/index.js", () => {
  return {
    Server: jest.fn().mockImplementation(() => {
      return {
        setRequestHandler: (schema: any, handler: Function) => {
          mockHandlers.set(schema, handler);
        },
        connect: jest.fn().mockResolvedValue(undefined),
      };
    }),
  };
});

// Mock child_process execSync
const mockExecSync = jest.fn();
jest.mock("child_process", () => ({
  execSync: (cmd: string) => mockExecSync(cmd),
}));

// Mock @solana/web3.js
jest.mock("@solana/web3.js", () => {
  const mockPublicKey = jest.fn().mockImplementation((val) => ({
    toBase58: () => val,
  }));
  return {
    Connection: jest.fn().mockImplementation(() => {
      return {
        getBalance: jest.fn().mockResolvedValue(1.5 * 1e9), // 1.5 SOL
      };
    }),
    PublicKey: mockPublicKey,
    Keypair: {
      fromSecretKey: jest.fn().mockReturnValue({
        publicKey: { toBase58: () => "mock_sniper_address" },
      }),
    },
  };
});

// Mock Argon2 & Tweetnacl
jest.mock("argon2", () => ({
  argon2id: "argon2id",
  hash: jest.fn().mockResolvedValue(Buffer.from("mock_derived_key")),
}));

jest.mock("tweetnacl", () => ({
  secretbox: {
    open: jest.fn().mockReturnValue(new Uint8Array(64)),
  },
}));

// Mock pg (Postgres client)
jest.mock("pg", () => {
  const mockPool = {
    query: jest.fn().mockImplementation((queryText) => {
      if (queryText.includes("GROUP BY state")) {
        return Promise.resolve({ rows: [{ state: "CLOSED", count: 5 }] });
      }
      if (queryText.includes("SUM(realised_pnl_sol)") || queryText.includes("SUM(")) {
        return Promise.resolve({ rows: [{ total: 0.25 }] });
      }
      if (queryText.includes("realised_pnl_sol")) {
        return Promise.resolve({
          rows: [
            {
              position_id: "pos1",
              mint: "mint1",
              state: "CLOSED",
              entry_price_sol: 0.1,
              realised_pnl_sol: 0.05,
              updated_at: new Date(),
            },
          ],
        });
      }
      return Promise.resolve({ rows: [] });
    }),
    end: jest.fn().mockResolvedValue(undefined),
  };
  return {
    Pool: jest.fn().mockImplementation(() => mockPool),
  };
});

// Mock fs and path
import fs from "fs";
import path from "path";
import yaml from "js-yaml";

jest.spyOn(fs, "readFileSync").mockImplementation((filePath: any) => {
  if (filePath.toString().includes("config.yaml")) {
    return `
wallets:
  sniper_keystore_path: "./keystores/sniper.keystore"
trading:
  position_size_sol: 0.005
  tp1_multiplier: 1.25
  tp2_multiplier: 1.25
  sl_multiplier: 0.95
  priority_fee_sol: 0.005
rpc:
  providers:
    - name: helius
      http_url: "https://mainnet.helius-rpc.com/?api-key=test"
      priority: 1
`;
  }
  if (filePath.toString().includes("sniper.keystore")) {
    return JSON.stringify({
      salt: "123456",
      nonce: "7890",
      encryptedSecretKey: "abc",
    });
  }
  return "";
});

const mockWriteFileSync = jest.spyOn(fs, "writeFileSync").mockImplementation(() => {});
jest.spyOn(fs, "existsSync").mockImplementation((p: any) => {
  if (p.toString().includes("config.yaml") || p.toString().includes("sniper.keystore")) {
    return true;
  }
  return false;
});

// Import index.ts after mocks have been declared
import { ListToolsRequestSchema, CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import "./index";

describe("MTUS MCP Server Tests", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockExecSync.mockReset();
  });

  test("ListToolsRequestSchema returns all registered tools", async () => {
    const listHandler = mockHandlers.get(ListToolsRequestSchema);
    expect(listHandler).toBeDefined();

    const response = await listHandler!();
    expect(response.tools).toBeDefined();
    expect(response.tools.length).toBe(4);
    
    const toolNames = response.tools.map((t: any) => t.name);
    expect(toolNames).toContain("get_system_status");
    expect(toolNames).toContain("update_trading_config");
    expect(toolNames).toContain("get_performance_report");
    expect(toolNames).toContain("trigger_maintenance");
  });

  test("CallToolRequestSchema get_system_status returns real status and balance", async () => {
    const callHandler = mockHandlers.get(CallToolRequestSchema);
    expect(callHandler).toBeDefined();

    mockExecSync.mockReturnValueOnce(
      JSON.stringify([
        {
          name: "ares-executor",
          pm2_env: { status: "online" },
          monit: { cpu: 1.2, memory: 45000000 },
        },
      ])
    );

    process.env.SNIPER_PASSPHRASE = "MTUS_2025_Sniper#X9kZ";

    const response = await callHandler!({
      params: {
        name: "get_system_status",
      },
    });

    expect(response.isError).toBeUndefined();
    const data = JSON.parse(response.content[0].text);
    expect(data.pm2[0].name).toBe("ares-executor");
    expect(data.sniper_balance).toBe("1.5000 SOL");
    expect(data.config_active.position_size).toBe(0.005);
    expect(data.config_active.risk.tp1_multiplier).toBe(1.25);
  });

  test("CallToolRequestSchema update_trading_config updates parameters and restarts PM2", async () => {
    const callHandler = mockHandlers.get(CallToolRequestSchema);
    expect(callHandler).toBeDefined();

    const response = await callHandler!({
      params: {
        name: "update_trading_config",
        arguments: {
          positionSizeSOL: 0.01,
          tp1_multiplier: 1.5,
          sl_multiplier: 0.9,
          priorityFeeSOL: 0.008,
        },
      },
    });

    expect(response.isError).toBeUndefined();
    expect(response.content[0].text).toContain("Configuration updated");

    // Check YAML written
    expect(mockWriteFileSync).toHaveBeenCalled();
    const [writtenPath, writtenContent] = mockWriteFileSync.mock.calls[0];
    expect(writtenContent).toContain("position_size_sol: 0.01");
    expect(writtenContent).toContain("tp1_multiplier: 1.5");
    expect(writtenContent).toContain("sl_multiplier: 0.9");
    expect(writtenContent).toContain("priority_fee_sol: 0.008");

    // Check PM2 restart was called
    expect(mockExecSync).toHaveBeenCalledWith("pm2 restart all");
  });

  test("CallToolRequestSchema get_performance_report returns stats and trade history", async () => {
    const callHandler = mockHandlers.get(CallToolRequestSchema);
    expect(callHandler).toBeDefined();

    const response = await callHandler!({
      params: {
        name: "get_performance_report",
        arguments: {
          limit: 5,
        },
      },
    });

    expect(response.isError).toBeUndefined();
    const data = JSON.parse(response.content[0].text);
    expect(data.state_summary[0].state).toBe("CLOSED");
    expect(data.total_profit_sol).toBe(0.25);
    expect(data.recent_trades[0].position_id).toBe("pos1");
  });

  test("CallToolRequestSchema trigger_maintenance executes clean up", async () => {
    const callHandler = mockHandlers.get(CallToolRequestSchema);
    expect(callHandler).toBeDefined();

    mockExecSync.mockReturnValueOnce("TOTAL ESTIMATED RECLAIM: 0.004078 SOL");

    const response = await callHandler!({
      params: {
        name: "trigger_maintenance",
      },
    });

    expect(response.isError).toBeUndefined();
    expect(response.content[0].text).toContain("TOTAL ESTIMATED RECLAIM: 0.004078 SOL");
    expect(mockExecSync).toHaveBeenCalledWith(expect.stringContaining("burn_and_close_ata.js"));
  });

  test("CallToolRequestSchema returns error for unknown tool", async () => {
    const callHandler = mockHandlers.get(CallToolRequestSchema);
    expect(callHandler).toBeDefined();

    const response = await callHandler!({
      params: {
        name: "non_existent_tool",
      },
    });

    expect(response.isError).toBe(true);
    expect(response.content[0].text).toContain("Unknown tool");
  });
});
