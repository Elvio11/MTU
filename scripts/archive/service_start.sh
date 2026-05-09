#!/bin/bash
# Start all agents as proper background processes
# Uses double-fork to detach from parent

cd /mnt/d/Trader

start_agent() {
    local cmd="$1"
    local log="$2"
    nohup bash -c "$cmd" > "$log" 2>&1 &
    disown
}

echo "Starting MTUS agents..."

# TypeScript agents
start_agent "node dist/agents/ares_start.js" "logs/ares.log"
start_agent "node dist/agents/sentinel_start.js" "logs/sentinel.log"
start_agent "node dist/agents/janus_start.js" "logs/janus.log"

# Python agents  
start_agent "python3 -m src.python.agents.nofx" "logs/nofx.log"
start_agent "python3 -m src.python.agents.hermes" "logs/hermes.log"
start_agent "python3 -m src.python.agents.anansi" "logs/anansi.log"
start_agent "python3 -m src.python.agents.oracle" "logs/oracle.log"
start_agent "python3 -m src.python.agents.heracles" "logs/heracles.log"
start_agent "python3 -m src.python.agents.cassandra" "logs/cassandra.log"
start_agent "python3 -m src.python.agents.ledger" "logs/ledger.log"

sleep 3

echo "Done. Running processes:"
pgrep -a -f 'node dist/agents' | head -5
pgrep -a -f 'python3 -m src.python.agents' | head -5