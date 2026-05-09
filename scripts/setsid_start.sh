#!/bin/bash
# Start all agents using setsid to create new session
# This should keep them running after parent exits

cd /mnt/d/Trader

echo "Starting MTUS agents..."

# TypeScript agents - use setsid to create new session
setsid node dist/agents/ares_start.js >logs/ares.log 2>&1 &
setsid node dist/agents/sentinel_start.js >logs/sentinel.log 2>&1 &
setsid node dist/agents/janus_start.js >logs/janus.log 2>&1 &

# Python agents - use python -u for unbuffered output
setsid python3 -u -m src.python.agents.nofx >logs/nofx.log 2>&1 &
setsid python3 -u -m src.python.agents.hermes >logs/hermes.log 2>&1 &
setsid python3 -u -m src.python.agents.anansi >logs/anansi.log 2>&1 &
setsid python3 -u -m src.python.agents.oracle >logs/oracle.log 2>&1 &
setsid python3 -u -m src.python.agents.heracles >logs/heracles.log 2>&1 &
setsid python3 -u -m src.python.agents.cassandra >logs/cassandra.log 2>&1 &
setsid python3 -u -m src.python.agents.ledger >logs/ledger.log 2>&1 &

sleep 3

echo "Started. Checking processes..."
pgrep -a -f 'node dist/agents' 2>/dev/null || echo "No node processes found"
pgrep -a -f 'python3 -m src.python.agents' 2>/dev/null || echo "No python processes found"