#!/bin/bash
# Keep agents running in background - use this instead of source

cd /mnt/d/Trader

# Kill existing agents
pkill -f 'node dist/agents' 2>/dev/null || true
pkill -f 'python3 -m src.python.agents' 2>/dev/null || true
sleep 1

# Start TypeScript agents
node dist/agents/ares_start.js >logs/ares.log 2>&1 &
node dist/agents/sentinel_start.js >logs/sentinel.log 2>&1 &
node dist/agents/janus_start.js >logs/janus.log 2>&1 &

# Start Python agents
python3 -m src.python.agents.nofx >logs/nofx.log 2>&1 &
python3 -m src.python.agents.hermes >logs/hermes.log 2>&1 &
python3 -m src.python.agents.anansi >logs/anansi.log 2>&1 &
python3 -m src.python.agents.oracle >logs/oracle.log 2>&1 &
python3 -m src.python.agents.heracles >logs/heracles.log 2>&1 &
python3 -m src.python.agents.cassandra >logs/cassandra.log 2>&1 &
python3 -m src.python.agents.ledger >logs/ledger.log 2>&1 &

# Wait for agents to start
sleep 3

echo "All agents started. PIDs:"
echo "TypeScript:"
pgrep -f 'node dist/agents' | while read pid; do
    echo "  $pid"
done
echo "Python:"
pgrep -f 'python3 -m src.python.agents' | while read pid; do
    echo "  $pid"
done