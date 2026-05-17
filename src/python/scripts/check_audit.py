import sqlite3
import json

def check_audit():
    conn = sqlite3.connect("data/positions.db")
    c = conn.cursor()
    c.execute("SELECT id, event_type, agent_id, payload, timestamp_utc FROM audit_ledger WHERE timestamp_utc > '2026-05-13T15:00:00' ORDER BY id DESC")
    rows = c.fetchall()
    print(f"Found {len(rows)} events since 15:00 UTC")
    for row in rows:
        print(f"ID: {row[0]} | Type: {row[1]} | Agent: {row[2]} | Time: {row[4]}")
        if row[1] == "token_qualified":
             print(f"  QUALIFIED: {row[3][:100]}...")
        if row[1] == "trade_failed":
             print(f"  FAILED: {row[3]}")
    conn.close()

if __name__ == "__main__":
    check_audit()
