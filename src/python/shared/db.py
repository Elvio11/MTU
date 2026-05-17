"""
db.py — Shared PostgreSQL connection helper for Python agents.
Replaces all direct sqlite3.connect() calls across the Python codebase.
Reads DATABASE_URL from the environment (same var used by the TS side).
"""
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv("./.env")


def _build_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "mtus_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def get_connection() -> psycopg2.extensions.connection:
    """
    Return a new psycopg2 connection to the MTUS PostgreSQL database.
    Rows are returned as dicts (RealDictCursor).
    Callers are responsible for closing the connection.
    """
    conn = psycopg2.connect(
        _build_dsn(),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    return conn
