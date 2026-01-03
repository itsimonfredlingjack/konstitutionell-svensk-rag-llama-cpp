"""
Claude Code Stats Proxy Routes
Proxy till Claude Stats API på dev-maskinen (192.168.86.27:8765)
"""

import httpx
from fastapi import APIRouter
from datetime import datetime

router = APIRouter(prefix="/api/claude", tags=["claude"])

DEV_MACHINE_URL = "http://192.168.86.27:8765"


@router.get("/stats")
async def get_claude_stats() -> dict:
    """
    Proxy till Claude Stats API på dev-maskinen.
    Returnerar tokens, kostnad, modeller och aktiv status.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{DEV_MACHINE_URL}/api/all")
            
            if response.status_code == 200:
                return {
                    "success": True,
                    **response.json(),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            else:
                return {
                    "success": False,
                    "error": f"API returned {response.status_code}",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                
    except httpx.ConnectError:
        return {
            "success": False,
            "error": "Cannot connect to dev machine (192.168.86.27:8765)",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
