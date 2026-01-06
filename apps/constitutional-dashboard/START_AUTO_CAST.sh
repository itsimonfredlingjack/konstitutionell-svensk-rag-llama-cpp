#!/bin/bash
# AUTO-CAST: Start Dashboard + Auto-Cast to Nest Hub (Sovis)
# This script starts both the Flask dashboard server and the cast_manager keepalive

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR"

echo "🚀 AUTO-CAST: Constitutional Dashboard → Google Nest Hub"
echo "=================================================="
echo ""

# Activate venv if it exists
if [ -d "$REPO_ROOT/venv" ]; then
  source "$REPO_ROOT/venv/bin/activate"
  echo "✅ Using venv: $REPO_ROOT/venv"
fi

# Load environment variables
export DASHBOARD_HOST="${DASHBOARD_HOST:-0.0.0.0}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-5000}"
export CAST_DISPLAY_NAME="${CAST_DISPLAY_NAME:-Sovis}"
export CAST_KEEPALIVE_SECONDS="${CAST_KEEPALIVE_SECONDS:-30.0}"
export CAST_RECAST_BACKOFF_SECONDS="${CAST_RECAST_BACKOFF_SECONDS:-5.0}"
export DASHBOARD_STARTUP_WAIT_SECONDS="${DASHBOARD_STARTUP_WAIT_SECONDS:-20.0}"

# Get local IP for public URL (if not set)
if [ -z "$DASHBOARD_PUBLIC_URL" ]; then
  # Try to get local IP
  LOCAL_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "192.168.86.32")
  export DASHBOARD_PUBLIC_URL="http://${LOCAL_IP}:${DASHBOARD_PORT}"
fi

echo "📊 Dashboard Config:"
echo "   Host: $DASHBOARD_HOST"
echo "   Port: $DASHBOARD_PORT"
echo "   Public URL: $DASHBOARD_PUBLIC_URL"
echo ""
echo "📺 Cast Config:"
echo "   Device: $CAST_DISPLAY_NAME"
echo "   Keepalive: ${CAST_KEEPALIVE_SECONDS}s"
echo ""

# Check if catt is available
if ! command -v catt &> /dev/null; then
  echo "⚠️  WARNING: 'catt' not found. Install with: pip install catt"
  echo "   Casting will be skipped, but dashboard will still start."
  CAST_ENABLED=false
else
  echo "✅ catt found: $(which catt)"
  CAST_ENABLED=true
fi

echo ""
echo "Starting dashboard server..."
echo ""

# Start Flask app in background
cd "$DASHBOARD_DIR"
python3 app.py > /tmp/dashboard.log 2>&1 &
DASHBOARD_PID=$!

echo "✅ Dashboard started (PID: $DASHBOARD_PID)"
echo "   Logs: /tmp/dashboard.log"
echo ""

# Wait a moment for server to start
sleep 2

# Check if dashboard is running
if ! kill -0 $DASHBOARD_PID 2>/dev/null; then
  echo "❌ Dashboard failed to start. Check logs:"
  cat /tmp/dashboard.log
  exit 1
fi

# Start cast_manager if enabled
if [ "$CAST_ENABLED" = true ]; then
  echo "Starting auto-cast manager to Google Nest Hub 'Sovis'..."
  # Export required env vars for cast_manager
  export DASHBOARD_PUBLIC_URL
  export CAST_DISPLAY_NAME
  python3 cast_manager.py > /tmp/cast_manager.log 2>&1 &
  CAST_PID=$!
  echo "✅ Cast manager started (PID: $CAST_PID)"
  echo "   Logs: /tmp/cast_manager.log"
  echo ""
  # Wait a moment and verify cast
  sleep 3
  if kill -0 $CAST_PID 2>/dev/null; then
    echo "🎉 AUTO-CAST ACTIVE"
    echo "   Dashboard: $DASHBOARD_PUBLIC_URL"
    echo "   Casting to Google Nest Hub: $CAST_DISPLAY_NAME"
    echo "   Check logs: tail -f /tmp/cast_manager.log"
    echo ""
    echo "To stop: kill $DASHBOARD_PID $CAST_PID"
  else
    echo "⚠️  Cast manager may have failed. Check logs: /tmp/cast_manager.log"
    echo "   Dashboard still running (PID: $DASHBOARD_PID)"
  fi
else
  echo "🎉 Dashboard running (cast disabled)"
  echo "   URL: http://$DASHBOARD_HOST:$DASHBOARD_PORT"
  echo ""
  echo "To stop: kill $DASHBOARD_PID"
fi

# Wait for user interrupt
trap "echo ''; echo 'Stopping...'; kill $DASHBOARD_PID $CAST_PID 2>/dev/null; exit 0" INT TERM

wait
