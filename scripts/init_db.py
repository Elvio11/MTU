#!/usr/bin/env python3
"""
Initialize SQLite database for MTUS
Creates all required tables per Section 5.1 and 5.2
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "./data/positions.db"


def init_database():
    """Create all required SQLite tables"""

    # Ensure data directory exists
    os.makedirs("./data", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"Initializing database at {DB_PATH}")

    # Positions table (Section 5.2)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            position_id TEXT PRIMARY KEY,
            mint TEXT NOT NULL,
            token_name TEXT,
            token_symbol TEXT,
            entry_price_sol REAL,
            entry_amount_sol REAL,
            tokens_received REAL,
            entry_tx_signature TEXT,
            entry_timestamp_utc TEXT,
            state TEXT NOT NULL,
            tp1_price REAL,
            tp2_price REAL,
            sl_price REAL,
            peak_price_sol REAL,
            exit_price_sol REAL,
            exit_tx_signature TEXT,
            realised_pnl_sol REAL,
            qualification_report TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    print("✓ positions table created")

    # Audit Ledger (Section 5.1)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            envelope_id TEXT,
            agent_id TEXT,
            event_type TEXT,
            payload TEXT,
            timestamp_utc TEXT
        )
    """)
    print("✓ audit_ledger table created")

    # Paper Positions (Section 8.4)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_positions (
            position_id TEXT PRIMARY KEY,
            mint TEXT NOT NULL,
            token_name TEXT,
            token_symbol TEXT,
            entry_price_sol REAL,
            entry_amount_sol REAL,
            tokens_received REAL,
            entry_timestamp_utc TEXT,
            exit_price_sol REAL,
            exit_timestamp_utc TEXT,
            realised_pnl_sol REAL,
            state TEXT NOT NULL,
            is_paper INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    print("✓ paper_positions table created")

    # Agent Health (Section 5.1 - stored in Redis but mirror in SQLite)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_health (
            agent_id TEXT PRIMARY KEY,
            status TEXT,
            last_heartbeat_utc TEXT,
            error_message TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    print("✓ agent_health table created")

    # Daily PnL Summary
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            total_pnl_sol REAL DEFAULT 0,
            trade_count INTEGER DEFAULT 0,
            win_count INTEGER DEFAULT 0,
            loss_count INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    print("✓ daily_pnl table created")

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_state ON positions(state)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_mint ON positions(mint)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_ledger(timestamp_utc)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paper_date ON paper_positions(entry_timestamp_utc)"
    )
    print("✓ Indexes created")

    conn.commit()

    # Verify tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"\nDatabase initialized successfully!")
    print(f"Tables: {[t[0] for t in tables]}")

    conn.close()


if __name__ == "__main__":
    init_database()
