# WebSocket /ws/harvest Fix

## Problem
The Constitutional Dashboard was experiencing WebSocket connection errors:
```
WebSocket connection to 'ws://192.168.86.32:8000/ws/harvest' failed
```

The endpoint existed in `constitutional_routes.py` but was:
1. Sending wrong data structure (stage/message instead of HarvestProgress format)
2. Not properly registered (FastAPI routers don't automatically register WebSocket endpoints)

## Solution

### 1. Updated Data Structure
Changed `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/api/constitutional_routes.py`:

**Old format:**
```json
{
  "stage": "Fetching documents",
  "progress": 25,
  "message": "Downloading from riksdagen.se..."
}
```

**New format (matches TypeScript HarvestProgress interface):**
```json
{
  "documentsProcessed": 2500,
  "currentSource": "Riksdagen",
  "progress": 1.0,
  "totalDocuments": 250000,
  "eta": "49m"
}
```

### 2. Proper WebSocket Registration
WebSocket endpoints in FastAPI routers must be explicitly registered in `main.py`.

**Changes to `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/main.py`:**

1. Imported the function:
   ```python
   from .api.constitutional_routes import router as constitutional_router, harvest_websocket
   ```

2. Registered the WebSocket:
   ```python
   app.websocket("/ws/harvest")(harvest_websocket)
   ```

3. Removed the `@router.websocket()` decorator from `constitutional_routes.py`

### 3. Mock Data Implementation
The endpoint now sends realistic mock harvest progress:
- Simulates processing 250,000 documents
- Rotates through 6 Swedish government sources
- Updates every 30 seconds
- Calculates realistic ETA
- Automatically resets when complete (for demo purposes)

## Testing

Test script created at `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/test_harvest_ws.py`:

```bash
python3 test_harvest_ws.py
```

Output:
```
✅ All required fields present
📊 Progress: 1.0%
📁 Documents: 2,500 / 250,000
🔄 Source: Riksdagen
⏱️  ETA: 49m
```

## Files Modified

1. `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/main.py`
   - Import harvest_websocket function
   - Register WebSocket endpoint
   - Add to root endpoint documentation

2. `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/api/constitutional_routes.py`
   - Remove @router.websocket decorator
   - Update data structure to match HarvestProgress
   - Implement continuous mock data stream
   - Add proper error handling

## Verification

1. Backend service restarted:
   ```bash
   systemctl --user restart constitutional-ai-backend
   ```

2. Endpoint verified:
   ```bash
   curl http://localhost:8000/ | jq -r '.harvest'
   # Returns: ws://localhost:8000/ws/harvest
   ```

3. WebSocket connection tested successfully with Python client

## Dashboard Integration

The Constitutional Dashboard at `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/constitutional-dashboard` should now:
- Successfully connect to `ws://{hostname}:8000/ws/harvest`
- Receive properly formatted HarvestProgress updates
- Display real-time harvest status without errors

No changes needed to the frontend - it already had the correct interface defined.
