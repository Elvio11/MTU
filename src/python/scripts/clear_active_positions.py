"""
clear_active_positions.py — Emergency maintenance script.
Closes all OPEN positions in PostgreSQL and clears the Redis active-positions set.
"""
import sys
import os
import asyncio

# Allow running from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from dotenv import load_dotenv
load_dotenv("./.env")

from src.python.shared.db import get_connection

async def main():
    import aioredis

    # 1. Close all OPEN positions in PostgreSQL
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE positions SET state = 'CLOSED', updated_at = NOW()::TEXT WHERE state = 'OPEN'"
            )
            count = cur.rowcount
        conn.commit()
        conn.close()
        print(f"PostgreSQL: Updated {count} positions to CLOSED.")
    except Exception as e:
        print(f"PostgreSQL: Error: {e}")

    # 2. Clear Redis active-positions set
    try:
        redis = await aioredis.from_url("redis://localhost:6379", decode_responses=True)
        await redis.delete("mtus:active_positions")
        await redis.close()
        print("Redis: Cleared mtus:active_positions set.")
    except Exception as e:
        print(f"Redis: Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
