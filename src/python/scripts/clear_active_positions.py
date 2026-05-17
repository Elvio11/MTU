import sqlite3
import aioredis
import asyncio
import os

async def clear_positions():
    # 1. Clear SQLite
    db_path = "data/positions.db"
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE positions SET state = 'CLOSED' WHERE state != 'CLOSED'")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        print(f"SQLite: Updated {count} positions to CLOSED.")
    else:
        print("SQLite: DB not found at data/positions.db")

    # 2. Clear Redis
    try:
        redis = await aioredis.from_url("redis://localhost:6379", decode_responses=True)
        
        # Clear active positions set
        await redis.delete("mtus:active_positions")
        print("Redis: Cleared mtus:active_positions set.")
        
        # Clear position keys
        keys = await redis.keys("mtus:position:*")
        if keys:
            for key in keys:
                await redis.delete(key)
            print(f"Redis: Deleted {len(keys)} position keys.")
            
        # Clear dedup keys to allow re-trading if needed
        dedup_keys = await redis.keys("mtus:dedup:*")
        if dedup_keys:
            for key in dedup_keys:
                await redis.delete(key)
            print(f"Redis: Deleted {len(dedup_keys)} dedup keys.")

        await redis.close()
    except Exception as e:
        print(f"Redis: Error clearing keys: {e}")

if __name__ == "__main__":
    asyncio.run(clear_positions())
