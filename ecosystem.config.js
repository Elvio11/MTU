module.exports = {
  apps: [
    {
      name: "python-agents",
      cwd: __dirname,
      script: "run_all_agents.py",
      interpreter: "python",
      env: {
        PYTHONPATH: ".",
      },
    },
    {
      name: "telegram-bot",
      cwd: __dirname,
      script: "src/python/agents/telegram_bot_agent.py",
      interpreter: "python",
      env: {
        PYTHONPATH: ".",
      },
    },
    {
      name: "ares-executor",
      cwd: __dirname,
      script: "dist/agents/ares_start.js",
      node_args: "--max-old-space-size=4096",
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "sentinel-monitor",
      cwd: __dirname,
      script: "dist/agents/sentinel_start.js",
      node_args: "--max-old-space-size=4096",
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "janus-sweep",
      cwd: __dirname,
      script: "dist/agents/janus_start.js",
      node_args: "--max-old-space-size=4096",
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "dashboard-server",
      cwd: __dirname,
      script: "run_dashboard.py",
      interpreter: "python",
      env: {
        PYTHONPATH: ".",
      },
    }
  ],
};

