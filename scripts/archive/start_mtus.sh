#!/bin/bash
# MTUS Complete Startup Script
# Run in WSL: bash /mnt/d/Trader/scripts/start_mtus.sh

echo "========================================="
echo "MTUS - Complete System Startup"
echo "========================================="
echo "Date: $(date)"
echo ""

# Step 1: Check/Start Redis
echo "[1/4] Checking Redis..."
if ! redis-cli ping >/dev/null 2>&1; then
    echo "  Starting Redis..."
    redis-server --daemonize yes
    sleep 1
fi
redis-cli ping
echo "  ✅ Redis OK"

# Step 2: Create logs directory
mkdir -p /mnt/d/Trader/logs
echo "[2/4] Logs directory ready"

# Step 3: Start TypeScript agents
echo "[3/4] Starting TypeScript agents..."

cd /mnt/d/Trader

# Start Ares (AGT-05)
nohup node dist/agents/ares.js > logs/ares.log 2>&1 &
ARES_PID=$!
echo "  ✅ Ares (AGT-05) PID: $ARES_PID"

# Start Sentinel (AGT-06)
nohup node dist/agents/sentinel.js > logs/sentinel.log 2>&1 &
SENTINEL_PID=$!
echo "  ✅ Sentinel (AGT-06) PID: $SENTINEL_PID"

# Start Janus (AGT-07)
nohup node dist/agents/janus.js > logs/janus.log 2>&1 &
JANUS_PID=$!
echo "  ✅ Janus (AGT-07) PID: $JANUS_PID"

# Step 4: Save PIDs
echo "$ARES_PID" > logs/ares.pid
echo "$SENTINEL_PID" > logs/sentinel.pid
echo "$JANUS_PID" > logs/janus.pid

echo ""
echo "========================================="
echo "TypeScript Agents Started!"
echo "========================================="
echo "PIDs saved to logs/*.pid"
echo ""
echo "Log files:"
echo "  tail -f logs/ares.log"
echo "  tail -f logs/sentinel.log"
echo "  tail -f logs/janus.log"
echo ""
echo "To start Python agents, run:"
echo "  cd /mnt/d/Trader"
echo "  source venv/bin/activate"
echo "  python -m src.python.agents.nofx &"
echo "  python -m src.python.agents.hermes &"
echo "  python -m src.python.agents.ansi &"
echo "  python -m src.python.agents.oracle &"
echo "  python -m src.python.agents.cassandra &"
echo "  python -m src.python.agents.ledger &"
echo "  python -m src.python.agents.heracles &"
echo ""
echo "Check agent health:"
echo "  redis-cli GET mtus:agent:AGT-05:health"
echo "  redis-cli GET mtus:agent:AGT-06:health"
echo "  redis-cli GET mtus:agent:AGT-10:health"
