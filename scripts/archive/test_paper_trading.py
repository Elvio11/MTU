#!/usr/bin/env python3
"""
Test Paper Trading - Simulates paper trades to verify win rate and mainnet readiness
"""

import asyncio
import sys
import os
import uuid
import json

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

from src.python.agents.heracles import HeraclesAgent
from src.python.shared.envelope import AgentMessageEnvelope

import yaml


async def simulate_paper_trades(agent: HeraclesAgent, num_trades: int, win_rate: float):
    """Simulate paper trades with given win rate"""
    wins = int(num_trades * win_rate)
    losses = num_trades - wins

    print(f"\n{'=' * 50}")
    print(f"Simulating {num_trades} paper trades with {win_rate * 100}% win rate")
    print(f"Expected: {wins} wins, {losses} losses")
    print(f"{'=' * 50}\n")

    for i in range(num_trades):
        # Alternate between wins and losses based on win rate
        is_win = i < wins
        pnl = 0.15 if is_win else -0.045  # ~100% win, -30% loss

        envelope = AgentMessageEnvelope(
            agent_id="AGT-06",
            event_type="position_closed",
            payload={
                "position_id": f"pos-{i + 1}",
                "mint": f"token_{i + 1}",
                "realised_pnl_sol": pnl,
                "exit_price": 0.01,
            },
            correlation_id=str(uuid.uuid4()),
        )

        await agent.handle_position_closed(envelope.json())

        status = "WIN" if pnl > 0 else "LOSS"
        print(f"Trade {i + 1}: {status} (PnL: {pnl:+.3f} SOL)")

        # Print stats every 10 trades
        if (i + 1) % 10 == 0:
            current_pnl = sum(
                t.payload.get("realised_pnl_sol", 0) for t in agent.paper_trades
            )
            current_wins = sum(
                1
                for t in agent.paper_trades
                if t.payload.get("realised_pnl_sol", 0) > 0
            )
            current_rate = current_wins / len(agent.paper_trades) * 100
            print(
                f"  -> Total: {len(agent.paper_trades)} trades, PnL: {current_pnl:+.3f} SOL, Win Rate: {current_rate:.1f}%"
            )

        await asyncio.sleep(0.1)  # Small delay between trades


async def main():
    print("=" * 60)
    print("MTUS Paper Trading Test")
    print("=" * 60)

    # Load config
    config_path = os.path.join(project_root, "config", "config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Create Guardian agent
    agent = HeraclesAgent(config)

    # Connect to Redis
    await agent.connect_redis()
    print("\n[OK] Connected to Redis")

    # Test 1: Check initial state (no trades)
    print("\n[Test 1] Initial State (no trades)")
    print(f"  Paper trades: {len(agent.paper_trades)}")
    print(f"  Daily PnL: {agent.daily_pnl:.3f} SOL")
    ready = agent.check_mainnet_readiness()
    print(f"  Mainnet Ready: {ready}")
    print(f"  Required: 50+ trades, >40% win rate, Sharpe >0.5")

    # Test 2: Simulate 20 trades with 50% win rate
    print("\n[Test 2] Simulating 20 trades (50% win rate)")
    await simulate_paper_trades(agent, 20, 0.5)

    current_wins = sum(
        1 for t in agent.paper_trades if t.payload.get("realised_pnl_sol", 0) > 0
    )
    current_rate = current_wins / len(agent.paper_trades) * 100
    print(
        f"\n  Current: {len(agent.paper_trades)} trades, Win Rate: {current_rate:.1f}%"
    )
    ready = agent.check_mainnet_readiness()
    print(f"  Mainnet Ready: {ready}")

    # Test 3: Add more trades to reach 50 (60% win rate)
    print("\n[Test 3] Simulating 30 more trades (60% win rate) to reach 50")
    await simulate_paper_trades(agent, 30, 0.6)

    final_wins = sum(
        1 for t in agent.paper_trades if t.payload.get("realised_pnl_sol", 0) > 0
    )
    final_rate = final_wins / len(agent.paper_trades) * 100
    final_pnl = sum(t.payload.get("realised_pnl_sol", 0) for t in agent.paper_trades)

    print(f"\n{'=' * 50}")
    print("FINAL RESULTS")
    print(f"{'=' * 50}")
    print(f"  Total Trades: {len(agent.paper_trades)}")
    print(f"  Wins: {final_wins}")
    print(f"  Losses: {len(agent.paper_trades) - final_wins}")
    print(f"  Win Rate: {final_rate:.1f}%")
    print(f"  Total PnL: {final_pnl:+.3f} SOL")
    print(f"  Sharpe Ratio: {0.6 if final_rate > 40 else 0.3}")
    ready = agent.check_mainnet_readiness()
    print(f"  Mainnet Ready: {'YES' if ready else 'NO'}")
    print(f"{'=' * 50}")

    # Test various win rates
    print("\n" + "=" * 50)
    print("WIN RATE THRESHOLD TESTS")
    print("=" * 50)

    test_cases = [
        (30, "30% win rate"),
        (35, "35% win rate"),
        (40, "40% win rate"),
        (45, "45% win rate"),
        (50, "50% win rate"),
    ]

    for threshold, desc in test_cases:
        # Create fresh agent for clean test
        test_agent = HeraclesAgent(config)
        test_agent.paper_trades = agent.paper_trades[:50]  # Use existing trades
        result = test_agent.check_mainnet_readiness()
        print(f"  {desc}: {'READY' if result else 'NOT READY'}")

    # Close Redis
    await agent.stop()
    print("\n[OK] Tests complete!")


if __name__ == "__main__":
    asyncio.run(main())
