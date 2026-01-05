#!/bin/bash
# Quick test: Start dashboard and cast once

cd "$(dirname "$0")"
REPO_ROOT="$(cd ../.. && pwd)"

if [ -d "$REPO_ROOT/venv" ]; then
  source "$REPO_ROOT/venv/bin/activate"
fi

export DASHBOARD_HOST="0.0.0.0"
export DASHBOARD_PORT="5000"
export CAST_DISPLAY_NAME="Sovis"
export DASHBOARD_PUBLIC_URL="http://192.168.86.32:5000"

echo "🧪 Testing AUTO-CAST..."
echo ""

# Start dashboard in background
python3 app.py > /tmp/dashboard_test.log 2>&1 &
DASH_PID=$!
echo "✅ Dashboard started (PID: $DASH_PID)"

# Wait for server to be ready
echo "⏳ Waiting for dashboard to be ready..."
for i in {1..10}; do
  if curl -s http://localhost:5000/api/stats > /dev/null 2>&1; then
    echo "✅ Dashboard is ready!"
    break
  fi
  sleep 1
done

# Test cast
echo ""
echo "📺 Testing cast to Sovis..."
python3 -c "
from cast_manager import _resolve_catt_bin, _catt_cast_site
import os
catt_bin = _resolve_catt_bin()
url = os.getenv('DASHBOARD_PUBLIC_URL', 'http://192.168.86.32:5000')
device = os.getenv('CAST_DISPLAY_NAME', 'Sovis')
print(f'Casting {url} to {device}...')
try:
    _catt_cast_site(catt_bin, device, url)
    print('✅ Cast successful!')
except Exception as e:
    print(f'❌ Cast failed: {e}')
    exit(1)
"

# Cleanup
echo ""
echo "🧹 Cleaning up..."
kill $DASH_PID 2>/dev/null
echo "✅ Test complete"
