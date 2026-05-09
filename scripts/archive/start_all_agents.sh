#!/bin/bash
# MTUS Agent Startup Script
# Run in WSL: bash /mnt/d/Trader/scripts/start_all_agents.sh

set -e

PROJECT_DIR="/mnt/d/Trader"
cd "$PROJECT_DIR" || exit 1

echo "========================================="
echo "MTUS - Starting All Agents"
echo "========================================="
echo "Project Dir: $PROJECT_DIR"
echo "Date: $(date)"
echo ""

# Check Redis
echo "[1/6] Checking Redis..."
if ! redis-cli ping >/dev/null 2>&1; then
    echo "  Starting Redis..."
    redis-server --daemonize yes
    sleep 1
fi
redis-cli ping
echo "  ✅ Redis OK"

# Build TypeScript
echo "[2/6] Building TypeScript..."
npm run build
echo "  ✅ Build complete"

# Start Ares (AGT-05)
echo "[3/6] Starting Ares (AGT-05)..."
nohup node dist/agents/ares.js > logs/ares.log 2>&1 &
echo "  ✅ Ares PID: $!"

# Start Sentinel (AGT-06)
echo "[4/6] Starting Sentinel (AGT-06)..."
nohup node dist/agents/sentinel.js > logs/sentinel.log 2>&1 &
echo "  ✅ Sentinel PID: $!"

# Start Janus (AGT-07)
echo "[5/6] Starting Janus (AGT-07)..."
nohup node dist/agents/janus.js > logs/janus.log 2>&1 &
echo "  ✅ Janus PID: $!"

# Create logs directory
mkdir -p logs

echo ""
echo "========================================="
echo "TypeScript Agents Started!"
echo "========================================="
echo "Logs: logs/*.log"
echo ""
echo "To start Python agents, run:"
echo "  source venv/bin/activate"
echo "  python -m src.python.agents.nofx &"
echo "  python -m src.python.agents.hermes &"
echo "  python -m src.python.agents.ansi &"
echo "  python -m src.python.agents.oracle &"
echo "  python -m src.python.agents.cassandra &"
echo "  python -m src.python.agents.ledger &"
echo "  python -m src.python.agents.heracles &"
echo ""
echo "Check status: redis-cli GET mtus:agent:AGT-05:health"
