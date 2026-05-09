#!/bin/bash
# Run Python Agents for MTUS Meme Trader

cd /mnt/d/Trader

echo "========================================="
echo "Starting Python Agents..."
echo "========================================="

mkdir -p logs

# Start each Python agent in background
python3 -m src.python.agents.nofx > logs/nofx.log 2>&1 &
NOFX_PID=$!
echo "  ✓ NoFX (AGT-01) PID: $NOFX_PID"

python3 -m src.python.agents.hermes > logs/hermes.log 2>&1 &
HERMES_PID=$!
echo "  ✓ Hermes (AGT-02) PID: $HERMES_PID"

python3 -m src.python.agents.anansi > logs/anansi.log 2>&1 &
ANANSI_PID=$!
echo "  ✓ Anansi (AGT-03) PID: $ANANSI_PID"

python3 -m src.python.agents.oracle > logs/oracle.log 2>&1 &
ORACLE_PID=$!
echo "  ✓ Oracle (AGT-04) PID: $ORACLE_PID"

python3 -m src.python.agents.heracles > logs/heracles.log 2>&1 &
HERACLES_PID=$!
echo "  ✓ Heracles (AGT-10) PID: $HERACLES_PID"

# Optional agents
python3 -m src.python.agents.cassandra > logs/cassandra.log 2>&1 &
CASSANDRA_PID=$!
echo "  ✓ Cassandra PID: $CASSANDRA_PID"

python3 -m src.python.agents.ledger > logs/ledger.log 2>&1 &
LEDGER_PID=$!
echo "  ✓ Ledger PID: $LEDGER_PID"

# Save PIDs
echo "$NOFX_PID" > logs/nofx.pid
echo "$HERMES_PID" > logs/hermes.pid
echo "$ANANSI_PID" > logs/anansi.pid
echo "$ORACLE_PID" > logs/oracle.pid
echo "$HERACLES_PID" > logs/heracles.pid
echo "$CASSANDRA_PID" > logs/cassandra.pid
echo "$LEDGER_PID" > logs/ledger.pid

echo ""
echo "========================================="
echo "All Python Agents Started!"
echo "========================================="
echo ""

sleep 2

echo "Agent Status:"
for name in nofx hermes anansi oracle heracles cassandra ledger; do
    pidfile="logs/${name}.pid"
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        if ps -p $pid > /dev/null 2>&1; then
            echo "  ✅ $name running"
        else
            echo "  ❌ $name crashed"
        fi
    fi
done

echo ""
echo "Check logs:"
for name in nofx hermes anansi oracle heracles cassandra ledger; do
    echo "  tail -f logs/${name}.log"
done