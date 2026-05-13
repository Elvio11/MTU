import pytest
import os
import sqlite3
from src.python.shared.paper_trading import PaperTradingEngine

@pytest.fixture
def engine(tmp_path):
    db_file = tmp_path / "test_positions.db"
    return PaperTradingEngine(str(db_file))

def test_setup_tables(engine):
    cursor = engine.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_positions'")
    assert cursor.fetchone() is not None

def test_open_position(engine):
    pos_id = engine.open_position("mint1", "Token1", 0.1, 1.0, 10.0)
    assert pos_id is not None
    
    cursor = engine.db.execute("SELECT mint, state FROM paper_positions WHERE position_id = ?", (pos_id,))
    row = cursor.fetchone()
    assert row[0] == "mint1"
    assert row[1] == "OPEN"

def test_close_position(engine):
    pos_id = engine.open_position("mint1", "Token1", 10.0, 100.0, 10.0)
    pnl = engine.close_position(pos_id, 12.0)
    
    # pnl = (12 - 10) * (100 / 10) = 2 * 10 = 20
    assert pnl == 20.0
    
    cursor = engine.db.execute("SELECT state, realised_pnl_sol FROM paper_positions WHERE position_id = ?", (pos_id,))
    row = cursor.fetchone()
    assert row[0] == "CLOSED"
    assert row[1] == 20.0

def test_close_non_existent_position(engine):
    assert engine.close_position("non_existent", 10.0) == 0.0

def test_get_stats_not_ready(engine):
    engine.open_position("mint1", "Token1", 1.0, 1.0, 1.0)
    stats = engine.get_stats()
    assert stats["ready"] is False
    assert stats["trades"] == 0 # None closed yet

def test_get_stats_ready(engine):
    # Add 50 winning trades
    for i in range(50):
        pos_id = engine.open_position(f"mint{i}", "T", 1.0, 1.0, 1.0)
        engine.close_position(pos_id, 2.0)
        
    stats = engine.get_stats()
    assert stats["trades"] == 50
    assert stats["win_rate"] == 1.0
    assert stats["ready"] is True
    assert stats["sharpe"] == 0.6
