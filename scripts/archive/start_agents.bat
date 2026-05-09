@echo off
REM MTUS Agent Startup Script
REM Starts all Python trading agents

echo ========================================
echo MTUS Trading Agents Starting...
echo ========================================

cd /d D:\Trader

REM Load env vars
set PYTHONPATH=D:\Trader

echo.
echo [1/7] Starting Guardian (AGT-10)...
start /B python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); import yaml; exec(open('src/python/agents/heracles.py').read())" > logs\heracles.log 2>&1

timeout /t 3 /nobreak > nul

echo [2/7] Starting Radar (AGT-01)...
start /B python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); import yaml; exec(open('src/python/agents/nofx.py').read())" > logs\nofx.log 2>&1

echo [3/7] Starting Router (AGT-02)...
start /B python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); import yaml; exec(open('src/python/agents/hermes.py').read())" > logs\hermes.log 2>&1

echo [4/7] Starting Safety (AGT-03)...
start /B python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); import yaml; exec(open('src/python/agents/anansi.py').read())" > logs\anansi.log 2>&1

echo [5/7] Starting Price (AGT-04)...
start /B python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); import yaml; exec(open('src/python/agents/oracle.py').read())" > logs\oracle.log 2>&1

echo [6/7] Starting Social (AGT-08)...
start /B python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); import yaml; exec(open('src/python/agents/cassandra.py').read())" > logs\cassandra.log 2>&1

echo [7/7] Starting Audit (AGT-09)...
start /B python -c "import sys; sys.path.insert(0,'.'); from dotenv import load_dotenv; load_dotenv('.env'); import yaml; exec(open('src/python/agents/ledger.py').read())" > logs\ledger.log 2>&1

echo.
echo ========================================
echo All agents started!
echo Check logs folder for output
echo ========================================
echo.
echo Note: TypeScript agents require:
echo   npm run build
echo   node dist\agents\ares.js
echo   node dist\agents\sentinel.js
echo   node dist\agents\janus.js

pause