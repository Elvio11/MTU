module.exports = {
  apps: [
    {
      name: "python-agents",
      script: "run_all_agents.py",
      interpreter: "python",
      env: {
        PYTHONPATH: ".",
      },
    },
    {
      name: "telegram-bot",
      script: "src/python/agents/telegram_bot_agent.py",
      interpreter: "python",
      env: {
        PYTHONPATH: ".",
      },
    },
    {
      name: "ares-executor",
      script: "dist/agents/ares_start.js",
      node_args: "--max-old-space-size=4096",
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "sentinel-monitor",
      script: "dist/agents/sentinel_start.js",
      node_args: "--max-old-space-size=4096",
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "janus-sweep",
      script: "dist/agents/janus_start.js",
      node_args: "--max-old-space-size=4096",
      env: {
        NODE_ENV: "production",
      },
    },
    {
      name: "dashboard-server",
      script: "run_dashboard.py",
      interpreter: "python",
      env: {
        PYTHONPATH: ".",
      },
    }
  ],
};
