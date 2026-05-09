#!/bin/bash
# Complete MTUS Meme Trader Startup
# Run this script in WSL: bash scripts/start_all.sh

set -e

cd /mnt/d/Trader

echo "========================================="
echo "MTUS Meme Trader - Starting All Services"
echo "========================================="
echo ""

# Step 1: Check Redis
echo "[1/5] Checking Redis..."
if ! redis-cli ping >/dev/null 2>&1; then
    echo "  Starting Redis..."
    redis-server --daemonize yes
    sleep 1
fi
redis-cli ping
echo "  ✓ Redis OK"
echo ""

# Step 2: Build TypeScript if needed
echo "[2/5] Checking TypeScript build..."
if [ ! -f "dist/agents/ares_start.js" ]; then
    echo "  Building TypeScript..."
    npm run build
fi
echo "  ✓ Build OK"
echo ""

# Step 3: Start TypeScript Agents
echo "[3/5] Starting TypeScript Agents..."
mkdir -p logs

node dist/agents/ares_start.js >logs/ares.log 2>&1 &
echo "  ✓ Ares (AGT-05)"

node dist/agents/sentinel_start.js >logs/sentinel.log 2>&1 &
echo "  ✓ Sentinel (AGT-06)"

node dist/agents/janus_start.js >logs/janus.log 2>&1 &
echo "  ✓ Janus (AGT-07)"

sleep 2
echo "  ✓ TypeScript agents started"
echo ""

# Step 4: Start Python Agents
echo "[4/5] Starting Python Agents..."

# Start each agent in background with proper redirection
python3 -m src.python.agents.nofx >>logs/nofx.log 2>&1 &
echo "  ✓ NoFX (AGT-01)"

python3 -m src.python.agents.hermes >>logs/hermes.log 2>&1 &
echo "  ✓ Hermes (AGT-02)"

python3 -m src.python.agents.anansi >>logs/anansi.log 2>&1 &
echo "  ✓ Anansi (AGT-03)"

python3 -m src.python.agents.oracle >>logs/oracle.log 2>&1 &
echo "  ✓ Oracle (AGT-04)"

python3 -m src.python.agents.heracles >>logs/heracles.log 2>&1 &
echo "  ✓ Heracles (AGT-10)"

python3 -m src.python.agents.cassandra >>logs/cassandra.log 2>&1 &
echo "  ✓ Cassandra"

python3 -m src.python.agents.ledger >>logs/ledger.log 2>&1 &
echo "  ✓ Ledger"

sleep 3
echo "  ✓ Python agents started"
echo ""

# Step 5: Verify
echo "[5/5] Verifying services..."
echo ""
echo "TypeScript Agents:"
for name in ares sentinel janus; do
    if pgrep -f "node.*${name}" > /dev/null; then
        echo "  ✅ $name"
    else
        echo "  ❌ $name"
    fi
done

echo ""
echo "Python Agents:"
for name in nofx hermes anansi oracle heracles cassandra ledger; do
    if pgrep -f "python3.*${name}" > /dev/null; then
        echo "  ✅ $name"
    else
        echo "  ❌ $name"
    fi
done

echo ""
echo "========================================="
echo "MTUS Meme Trader - All Services Started!"
echo "========================================="
echo ""
echo "Check logs with:"
echo "  tail -f logs/ares.log"
echo "  tail -f logs/nofx.log"
echo "  etc."
echo ""
echo "Press Ctrl+C to stop all services"