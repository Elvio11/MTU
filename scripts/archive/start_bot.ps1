#!/bin/bash
# MTUS Bot Startup Script
# Starts all agents in paper trading mode

echo "=========================================="
echo "MTUS Trading Bot - Starting..."
echo "=========================================="

# Check Redis
echo "[1/5] Checking Redis..."
redis-cli ping > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  Redis: OK"
else
    echo "  Redis: NOT RUNNING - Starting..."
    start redis-server.exe
    sleep 2
fi

# Set environment
export MTUS_ENVIRONMENT=paper
echo "[2/5] Environment: paper trading"

# Load env variables
export TELEGRAM_BOT_TOKEN=8749737932:AAFoOtlO52eOdJsQgSlxha7A5cEWx4JekJg
export TELEGRAM_ADMIN_CHAT_ID=6060434624
export TELEGRAM_OTP_SEED=mtus_secure_otp_seed_x8k2m9p4q
export HELIUS_KEY=90b7db5c-9ecd-4f01-8c65-a886a8d1a67d
export ALCHEMY_URL=https://solana-mainnet.g.alchemy.com/v2/_qcAnZERSDa8eRymPiKUx
export BIRDEYE_API_KEY=222051cfe4bf467fab286b965fcefe60

echo "[3/5] Environment variables loaded"

# Create logs directory
mkdir -p logs

echo "[4/5] Starting agents..."
echo ""

# Start Telegram bot in background
python -m src.python.shared.telegram_bot &
TELEGRAM_PID=$!
echo "  Telegram Bot: PID $TELEGRAM_PID"

# Wait a moment for Redis to be ready
sleep 2

echo ""
echo "[5/5] All systems started!"
echo "=========================================="
echo "Bot running in PAPER trading mode"
echo "Telegram: Send /status to check"
echo "Logs: ./logs/"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop"

# Wait for interrupt
trap "echo 'Stopping MTUS...'; kill $TELEGRAM_PID 2>/dev/null; exit" INT TERM
wait