#!/usr/bin/env bash
# ===================================================================
# CheckMate — Quick Public Tunnel Launcher
# Launches CheckMate server & creates a secure public HTTPS URL
# ===================================================================

echo "⚡ Starting CheckMate Server on http://127.0.0.1:8765..."

# Select Python environment
if [ -d ".venv" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

# Launch CheckMate server in background if not running
if ! pgrep -f "python.*main.py" > /dev/null; then
    $PYTHON_BIN main.py > /dev/null 2>&1 &
    SERVER_PID=$!
    echo "✅ CheckMate Server started (PID: $SERVER_PID)"
    sleep 2
else
    echo "✅ CheckMate Server is already running"
fi

# Check for cloudflared
CLOUDFLARED_BIN=$(which cloudflared || echo "/opt/homebrew/bin/cloudflared")

if [ ! -f "$CLOUDFLARED_BIN" ]; then
    echo "❌ cloudflared is not installed. Installing via Homebrew..."
    brew install cloudflared
fi

echo "🌐 Requesting instant Public HTTPS Tunnel from Cloudflare..."
echo "-------------------------------------------------------------------"
$CLOUDFLARED_BIN tunnel --url http://127.0.0.1:8765
