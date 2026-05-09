#!/usr/bin/env python3
"""
Simple agent runner - imports and runs agents directly
"""

import sys
import os

# Setup path - go up one level from scripts to project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

print(f"Working directory: {os.getcwd()}")

# Load env
from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, ".env"))

import yaml

with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

import asyncio
from src.python.agents.heracles import HeraclesAgent


async def main():
    agent = HeraclesAgent(config)
    await agent.connect_redis()
    print("=" * 50)
    print("Guardian (AGT-10) Running...")
    print("=" * 50)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
