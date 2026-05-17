"""
check_audit.py — Diagnostic script to inspect the audit ledger in PostgreSQL.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from dotenv import load_dotenv
load_dotenv("./.env")

from src.python.shared.db import get_connection


def main():
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM audit_ledger ORDER BY timestamp_utc DESC LIMIT 20"
            )
            rows = cur.fetchall()
        conn.close()

        if not rows:
            print("Audit ledger is empty.")
            return

        print(f"Last {len(rows)} audit entries:")
        for row in rows:
            print(f"  [{row['timestamp_utc']}] {row['agent_id']} → {row['event_type']}")

    except Exception as e:
        print(f"Error querying audit ledger: {e}")


if __name__ == "__main__":
    main()
