import pytest
import asyncio
import sqlite3
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.python.agents.portfolio_sizer import PortfolioSizerAgent, main

class SqlitePostgresAdapter:
    def __init__(self, conn):
        self.conn = conn
    
    def cursor(self):
        class CursorWrapper:
            def __init__(self, cur):
                self.cur = cur
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                self.cur.close()
            def execute(self, query, params=None):
                if params:
                    query = query.replace("%s", "?")
                self.cur.execute(query, params or ())
            @property
            def rowcount(self):
                return self.cur.rowcount
            def fetchone(self):
                res = self.cur.fetchone()
                if res is None:
                    return None
                class RowWrapper(dict):
                    def __getitem__(self, key):
                        if isinstance(key, int):
                            return list(self.values())[key]
                        return super().__getitem__(key)
                cols = []
                for desc in self.cur.description:
                    col_name = desc[0].lower()
                    if "sum(" in col_name:
                        cols.append("sum")
                    else:
                        cols.append(col_name)
                return RowWrapper(dict(zip(cols, res)))
            def fetchall(self):
                res = self.cur.fetchall()
                if res is None:
                    return []
                cols = [desc[0].lower() for desc in self.cur.description]
                return [dict(zip(cols, row)) for row in res]
        return CursorWrapper(self.conn.cursor())
    
    def commit(self):
        self.conn.commit()
    def rollback(self):
        self.conn.rollback()
    def close(self):
        self.conn.close()

@pytest.fixture(autouse=True)
def mock_db_connection(portfolio_agent):
    def mock_get_conn():
        return SqlitePostgresAdapter(sqlite3.connect(portfolio_agent.db_path))
    with patch("src.python.agents.portfolio_sizer.get_connection", side_effect=mock_get_conn):
        yield

@pytest.fixture
def portfolio_agent(tmp_path):
    config = {
        "trading": {
            "position_size_sol": 0.001,
            "max_position_size_sol": 0.05,
            "compounding_pct": 0.2,
            "dynamic_growth_enabled": True,
        }
    }
    agent = PortfolioSizerAgent(config)
    agent.redis = AsyncMock()
    # Mock DB path to temp file
    db_file = tmp_path / "positions.db"
    agent.db_path = str(db_file)
    return agent


@pytest.mark.asyncio
async def test_portfolio_connect_redis(portfolio_agent):
    with patch("aioredis.from_url", new_callable=AsyncMock) as mock_redis:
        mock_r = AsyncMock()
        mock_redis.return_value = mock_r
        mock_r.pubsub = MagicMock(return_value=AsyncMock())
        await portfolio_agent.connect_redis()
        assert portfolio_agent.redis == mock_r


def test_portfolio_calculate_new_size_no_db(portfolio_agent):
    # Should return base size if DB doesn't exist
    assert portfolio_agent.calculate_new_size() == 0.001


def test_portfolio_calculate_new_size_with_data(portfolio_agent):
    # Create DB and add data
    conn = sqlite3.connect(portfolio_agent.db_path)
    conn.execute("CREATE TABLE positions (state TEXT, realised_pnl_sol REAL)")
    conn.execute("INSERT INTO positions VALUES ('CLOSED', 0.1)")
    conn.commit()
    conn.close()

    # Base (0.001) + (0.2 * 0.1) = 0.001 + 0.02 = 0.021
    assert portfolio_agent.calculate_new_size() == pytest.approx(0.021)


def test_portfolio_calculate_new_size_disabled(portfolio_agent):
    portfolio_agent.growth_enabled = False
    conn = sqlite3.connect(portfolio_agent.db_path)
    conn.execute("CREATE TABLE positions (state TEXT, realised_pnl_sol REAL)")
    conn.execute("INSERT INTO positions VALUES ('CLOSED', 0.1)")
    conn.commit()
    conn.close()

    assert portfolio_agent.calculate_new_size() == 0.001


def test_portfolio_calculate_new_size_negative_pnl(portfolio_agent):
    conn = sqlite3.connect(portfolio_agent.db_path)
    conn.execute("CREATE TABLE positions (state TEXT, realised_pnl_sol REAL)")
    conn.execute("INSERT INTO positions VALUES ('CLOSED', -0.1)")
    conn.commit()
    conn.close()

    assert portfolio_agent.calculate_new_size() == 0.001


def test_portfolio_calculate_new_size_capped(portfolio_agent):
    conn = sqlite3.connect(portfolio_agent.db_path)
    conn.execute("CREATE TABLE positions (state TEXT, realised_pnl_sol REAL)")
    conn.execute("INSERT INTO positions VALUES ('CLOSED', 1.0)")
    conn.commit()
    conn.close()

    # Base (0.001) + (0.2 * 1.0) = 0.201, capped at 0.05
    assert portfolio_agent.calculate_new_size() == 0.05


@pytest.mark.asyncio
async def test_portfolio_update_redis_config(portfolio_agent):
    portfolio_agent.calculate_new_size = MagicMock(return_value=0.0123)
    await portfolio_agent.update_redis_config()
    portfolio_agent.redis.set.assert_called_with("mtus:position_size_sol", "0.0123")


@pytest.mark.asyncio
async def test_portfolio_run_loop(portfolio_agent):
    portfolio_agent.pubsub = AsyncMock()
    portfolio_agent.update_redis_config = AsyncMock()

    # Return a message once then stop
    call_count = 0

    async def mock_get_message(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"data": "closed"}
        portfolio_agent.running = False
        return None

    portfolio_agent.pubsub.get_message = mock_get_message

    with (
        patch(
            "src.python.agents.portfolio_sizer.is_operational_window_active",
            return_value=True,
        ),
        patch.object(portfolio_agent, "connect_redis", new_callable=AsyncMock),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await portfolio_agent.run()

    assert portfolio_agent.update_redis_config.call_count >= 1


@pytest.mark.asyncio
async def test_portfolio_stop(portfolio_agent):
    portfolio_agent.pubsub = AsyncMock()
    await portfolio_agent.stop()
    portfolio_agent.redis.close.assert_called_once()
    portfolio_agent.pubsub.unsubscribe.assert_called_once()


@pytest.mark.asyncio
async def test_portfolio_main_keyboard_interrupt():
    m = mock_open(read_data="trading:\n  position_size_sol: 0.1\n")
    with (
        patch("src.python.agents.portfolio_sizer.open", m),
        patch(
            "src.python.agents.portfolio_sizer.PortfolioSizerAgent"
        ) as mock_agent_class,
        patch(
            "src.python.agents.portfolio_sizer.validate_config",
            return_value=(True, None),
        ),
    ):
        mock_agent_instance = mock_agent_class.return_value
        mock_agent_instance.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_agent_instance.stop = AsyncMock()

        await main()
        assert mock_agent_instance.run.called
        assert mock_agent_instance.stop.called


@pytest.mark.asyncio
async def test_portfolio_main_config_error():
    m = mock_open(read_data="trading:\n  position_size_sol: 0.1\n")
    with (
        patch("src.python.agents.portfolio_sizer.open", m),
        patch(
            "src.python.agents.portfolio_sizer.validate_config",
            return_value=(False, "error"),
        ),
        patch("sys.exit", side_effect=SystemExit(1)) as mock_exit,
    ):
        with pytest.raises(SystemExit) as exc:
            await main()
        assert exc.value.code == 1


def test_portfolio_calculate_new_size_exception(portfolio_agent):
    """Lines 74-76: calculate_new_size exception handled."""
    open(portfolio_agent.db_path, "w").close()
    with patch("sqlite3.connect", side_effect=Exception("DB error")):
        assert portfolio_agent.calculate_new_size() == 0.001


@pytest.mark.asyncio
async def test_portfolio_update_redis_config_exception(portfolio_agent):
    portfolio_agent.redis.set.side_effect = Exception("Redis error")
    # Should catch and log, not raise
    await portfolio_agent.update_redis_config()


@pytest.mark.asyncio
async def test_portfolio_main_open_exception():
    with (
        patch(
            "src.python.agents.portfolio_sizer.open",
            side_effect=Exception("Open Error"),
        ),
        patch("sys.exit", side_effect=SystemExit(1)) as mock_exit,
    ):
        with pytest.raises(SystemExit) as exc:
            await main()
        assert exc.value.code == 1


@pytest.mark.asyncio
async def test_portfolio_calculate_new_size_generic_exception(portfolio_agent):
    with patch("sqlite3.connect", side_effect=Exception("Generic Error")):
        assert portfolio_agent.calculate_new_size() == 0.001


@pytest.mark.asyncio
async def test_portfolio_run_loop_exception(portfolio_agent):
    portfolio_agent.pubsub = AsyncMock()
    portfolio_agent.update_redis_config = AsyncMock()

    call_count = 0

    async def mock_get_message(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Loop Error")
        portfolio_agent.running = False
        return None

    portfolio_agent.pubsub.get_message = mock_get_message

    with (
        patch(
            "src.python.agents.portfolio_sizer.is_operational_window_active",
            return_value=True,
        ),
        patch.object(portfolio_agent, "connect_redis", new_callable=AsyncMock),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await portfolio_agent.run()

    assert call_count >= 1
