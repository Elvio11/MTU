#!/bin/bash
# Run MTUS Meme Trader - Complete Setup
# This script runs in WSL

set -e

echo "========================================="
echo "MTUS Meme Trader - Starting..."
echo "========================================="
echo "Date: $(date)"
echo ""

# Step 1: Check Redis
echo "[1/4] Checking Redis..."
if ! redis-cli ping >/dev/null 2>&1; then
    echo "  Starting Redis..."
    redis-server --daemonize yes
    sleep 1
fi
redis-cli ping
echo "  ✓ Redis OK"

# Step 2: Build if needed
echo "[2/4] Checking build..."
cd /mnt/d/Trader
if [ ! -f "dist/agents/ares.js" ]; then
    echo "  Building TypeScript..."
    npm run build
fi
echo "  ✓ Build OK"

# Step 3: Create logs directory
echo "[3/4] Setting up logs..."
mkdir -p logs
echo "  ✓ Logs directory ready"

# Step 4: Start agents
echo "[4/4] Starting agents..."

# Start Ares (AGT-05)
node dist/agents/ares_start.js >logs/ares.log 2>&1 &
ARES_PID=$!
echo "  ✓ Ares (AGT-05) PID: $ARES_PID"

# Start Sentinel (AGT-06)
node dist/agents/sentinel_start.js >logs/sentinel.log 2>&1 &
SENTINEL_PID=$!
echo "  ✓ Sentinel (AGT-06) PID: $SENTINEL_PID"

# Start Janus (AGT-07)
node dist/agents/janus_start.js >logs/janus.log 2>&1 &
JANUS_PID=$!
echo "  ✓ Janus (AGT-07) PID: $JANUS_PID"

# Save PIDs
echo "$ARES_PID" > logs/ares.pid
echo "$SENTINEL_PID" > logs/sentinel.pid
echo "$JANUS_PID" > logs/janus.pid

echo ""
echo "========================================="
echo "MTUS TypeScript Agents Started!"
echo "========================================="
echo "PIDs saved to logs/*.pid"

echo ""
echo "Check logs:"
echo "  tail -f logs/ares.log"
echo "  tail -f logs/sentinel.log"
echo "  tail -f logs/janus.log"

echo ""
echo "Waiting for agents to initialize..."
sleep 3

echo ""
echo "Agent Status:"
if ps -p $ARES_PID >/dev/null 2>&1; then
    echo "  ✅ Ares (AGT-05) running"
else
    echo "  ❌ Ares crashed - check logs/ares.log"
fi

if ps -p $SENTINEL_PID >/dev/null 2>&1; then
    echo "  ✅ Sentinel (AGT-06) running"
else
    echo "  ❌ Sentinel crashed - check logs/sentinel.log"
fi

if ps -p $JANUS_PID >/dev/null 2>&1; then
    echo "  ✅ Janus (AGT-07) running"
else
    echo "  ❌ Janus crashed - check logs/janus.log"
fi

echo ""
echo "To start Python agents, run:"
echo "  cd /mnt/d/Trader"
echo "  source venv/bin/activate"
echo "  python -m src.python.agents.nofx &"
echo "  python -m src.python.agents.hermes &"
echo "  python -m src.python.agents.anansi &"
echo "  python -m src.python.agents.oracle &"
echo "  python -m src.python.agents.cassandra &"
echo "  python -m src.python.agents.ledger &"
echo "  python -m src.python.agents.heracles &"

echo ""
echo "Startup complete! Waiting for agents (press Ctrl+C to stop)..."
wait
