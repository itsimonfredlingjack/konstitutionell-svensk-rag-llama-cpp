#!/usr/bin/env python3
"""
Quick test script to verify /ws/harvest WebSocket endpoint
Tests that the endpoint returns correct HarvestProgress data structure
"""

import asyncio
import json

import websockets


async def test_harvest_websocket():
    uri = "ws://localhost:8000/ws/harvest"

    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as websocket:
            print("Connected! Waiting for messages...")

            # Receive 3 messages to verify format
            for i in range(3):
                message = await websocket.recv()
                data = json.loads(message)

                print(f"\nMessage {i+1}:")
                print(json.dumps(data, indent=2))

                # Verify expected fields
                required_fields = [
                    "documentsProcessed",
                    "currentSource",
                    "progress",
                    "totalDocuments",
                ]
                missing = [f for f in required_fields if f not in data]

                if missing:
                    print(f"  ❌ Missing fields: {missing}")
                else:
                    print("  ✅ All required fields present")
                    print(f"  📊 Progress: {data['progress']}%")
                    print(
                        f"  📁 Documents: {data['documentsProcessed']:,} / {data['totalDocuments']:,}"
                    )
                    print(f"  🔄 Source: {data['currentSource']}")
                    if data.get("eta"):
                        print(f"  ⏱️  ETA: {data['eta']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    print("\n✅ WebSocket test completed successfully!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_harvest_websocket())
    exit(0 if success else 1)
