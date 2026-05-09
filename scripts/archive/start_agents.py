#!/usr/bin/env python3
"""
Start all MTUS Trading Agents
"""

import sys
import os
import asyncio
import subprocess

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

# Load environment variables
from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, ".env"))

from src.python.agents.heracles import HeraclesAgent
from src.python.agents.nofx import NofxAgent
from src.python.agents.hermes import HermesAgent
from src.python.agents.anansi import AnansiAgent
from src.python.agents.oracle import OracleAgent
from src.python.agents.cassandra import CassandraAgent
from src.python.agents.ledger import LedgerAgent

import yaml


async def start_agent(agent_class, config, name):
    """Start an agent and handle errors"""
    try:
        agent = agent_class(config)
        if hasattr(agent, "connect_redis"):
            await agent.connect_redis()
        print(f"[OK] {name}")
        if hasattr(agent, "run"):
            await agent.run()
    except Exception as e:
        print(f"[ERROR] {name}: {e}")


async def main():
    print("=" * 50)
    print("MTUS Trading Agents Starting...")
    print("=" * 50)

    # Load config
    config_path = os.path.join(project_root, "config", "config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    print(f"\nEnvironment: {config.get('system', {}).get('environment', 'unknown')}")
    print(f"Trading Active: {config.get('system', {}).get('trading_active', False)}")
    print("")

    # Start Guardian (AGT-10) - must start first
    print("[1/7] Starting Guardian (AGT-10)...")
    heracles = HeraclesAgent(config)
    await heracles.connect_redis()
    print("[OK] Guardian (AGT-10)")

    # Start other agents
    agents = [
        (NofxAgent, config, "Radar (AGT-01)"),
        (HermesAgent, config, "Router (AGT-02)"),
        (AnansiAgent, config, "Safety (AGT-03)"),
        (OracleAgent, config, "Price (AGT-04)"),
        (CassandraAgent, config, "Social (AGT-08)"),
        (LedgerAgent, config, "Audit (AGT-09)"),
    ]

    for i, (agent_class, cfg, name) in enumerate(agents, start=2):
        print(f"[{i}/7] Starting {name}...")
        try:
            agent = agent_class(cfg)
            if hasattr(agent, "connect_redis"):
                await agent.connect_redis()
            print(f"[OK] {name}")
        except Exception as e:
            print(f"[WARN] {name}: {e}")

    print("\n" + "=" * 50)
    print("All Python Agents Started!")
    print("=" * 50)
    print("\nNOTE: TypeScript agents (Ares, Sentinel, Janus)")
    print("      require: npm run build")
    print("      Then: node dist/agents/ares.js")
    print("")
    print("Press Ctrl+C to stop...")

    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nStopping agents...")
        if heracles.running:
            await heracles.stop()


if __name__ == "__main__":
    asyncio.run(main())
