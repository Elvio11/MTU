#!/bin/bash
# Debug script - run in WSL
cd /mnt/d/Trader

echo "Running Ares agent for 5 seconds..."
timeout 5s node dist/agents/ares.js > /tmp/ares_debug.log 2>&1
EXIT_CODE=$?
echo "Exit code: $EXIT_CODE"
echo ""
echo "Last 50 lines of log:"
tail -50 /tmp/ares_debug.log
echo ""

echo "Checking if process is still running..."
ps aux | grep "ares.js" | grep -v grep || echo "NOT RUNNING"
