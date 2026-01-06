#!/bin/bash
# Start Constitutional Dashboard for Nest Hub (Sovis)

cd "$(dirname "$0")"
REPO_ROOT="$(cd ../.. && pwd)"

echo "🚀 Starting Constitutional Dashboard..."
echo "   Target: Google Nest Hub (1024x600)"
echo "   URL: http://0.0.0.0:5000"
echo ""

# Activate venv if it exists
if [ -d "$REPO_ROOT/venv" ]; then
  source "$REPO_ROOT/venv/bin/activate"
  echo "✅ Using venv: $REPO_ROOT/venv"
fi

# Start Flask app
export DASHBOARD_HOST="${DASHBOARD_HOST:-0.0.0.0}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-5000}"
export CAST_DISPLAY_NAME="${CAST_DISPLAY_NAME:-Sovis}"

python3 app.py
