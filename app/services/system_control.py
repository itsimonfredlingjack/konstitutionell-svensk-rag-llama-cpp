"""
System Control Functions for Kiosk Dashboard
Provides async functions for managing backend/frontend services and models
"""

import asyncio
import httpx
from typing import Dict, List, Any

from .ollama_client import ollama_client
from ..models.Backend_Agent_Prompts import ProfileId, get_profile
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Ollama API endpoint for unloading models
OLLAMA_GENERATE_ENDPOINT = "http://localhost:11434/api/generate"


async def warmup_model() -> Dict[str, Any]:
    """
    Warmup the CASCADE-PLANNER model using the existing ollama_client.

    Returns:
        Dict with success status and message
    """
    try:
        logger.info("Starting model warmup for cascade-planner")

        # Get the CASCADE-PLANNER profile
        profile = get_profile(ProfileId.CASCADE_PLANNER)

        # Use the ollama_client warmup function
        success = await ollama_client.warmup_model(profile)

        if success:
            logger.info("Model warmup completed successfully")
            return {
                "success": True,
                "message": f"Model {profile.model} warmed up successfully",
                "model": profile.model
            }
        else:
            logger.error("Model warmup failed")
            return {
                "success": False,
                "message": f"Failed to warmup model {profile.model}",
                "model": profile.model
            }

    except Exception as e:
        logger.error(f"Error during model warmup: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error during warmup: {str(e)}",
            "error": str(e)
        }


async def restart_backend() -> Dict[str, Any]:
    """
    Restart the simons-ai-backend systemd service.

    Returns:
        Dict with success status and message
    """
    try:
        logger.info("Attempting to restart simons-ai-backend service")

        # Run systemctl restart command
        process = await asyncio.create_subprocess_exec(
            "sudo", "systemctl", "restart", "simons-ai-backend",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info("Backend service restarted successfully")
            return {
                "success": True,
                "message": "Backend service restarted successfully",
                "service": "simons-ai-backend"
            }
        else:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            logger.error(f"Failed to restart backend service: {error_msg}")
            return {
                "success": False,
                "message": f"Failed to restart backend: {error_msg}",
                "service": "simons-ai-backend",
                "error": error_msg
            }

    except Exception as e:
        logger.error(f"Error restarting backend service: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error restarting backend: {str(e)}",
            "service": "simons-ai-backend",
            "error": str(e)
        }


async def recast_dashboard() -> Dict[str, Any]:
    """
    Cast dashboard to Nest Hub "Sovis" using catt.

    Returns:
        Dict with success status and message
    """
    try:
        logger.info("Casting dashboard to Nest Hub Sovis")

        process = await asyncio.create_subprocess_exec(
            "/home/ai-server/catt-venv/bin/catt",
            "-d", "Sovis",
            "cast_site", "http://192.168.86.32:5173/kiosk",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info("Dashboard cast to Sovis successfully")
            return {
                "success": True,
                "message": "Dashboard cast to Sovis",
                "device": "Sovis"
            }
        else:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            logger.error(f"Failed to cast dashboard: {error_msg}")
            return {
                "success": False,
                "message": f"Failed to cast: {error_msg}",
                "device": "Sovis",
                "error": error_msg
            }

    except Exception as e:
        logger.error(f"Error casting dashboard: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error casting: {str(e)}",
            "device": "Sovis",
            "error": str(e)
        }


async def restart_frontend() -> Dict[str, Any]:
    """
    Restart the simons-ai-frontend systemd service and recast dashboard.

    Returns:
        Dict with success status and message
    """
    try:
        logger.info("Attempting to restart simons-ai-frontend service")

        # Run systemctl restart command
        process = await asyncio.create_subprocess_exec(
            "sudo", "systemctl", "restart", "simons-ai-frontend",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info("Frontend service restarted successfully")

            # Wait for frontend to be ready and recast dashboard
            logger.info("Waiting 5s for frontend to start, then recasting...")
            await asyncio.sleep(5)
            cast_result = await recast_dashboard()

            return {
                "success": True,
                "message": "Frontend restarted and dashboard recast",
                "service": "simons-ai-frontend",
                "cast_result": cast_result
            }
        else:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            logger.error(f"Failed to restart frontend service: {error_msg}")
            return {
                "success": False,
                "message": f"Failed to restart frontend: {error_msg}",
                "service": "simons-ai-frontend",
                "error": error_msg
            }

    except Exception as e:
        logger.error(f"Error restarting frontend service: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error restarting frontend: {str(e)}",
            "service": "simons-ai-frontend",
            "error": str(e)
        }


async def unload_all_models() -> Dict[str, Any]:
    """
    Unload all running models from Ollama by setting keep_alive=0.

    Returns:
        Dict with success status and list of unloaded models
    """
    try:
        logger.info("Attempting to unload all models")

        # First, get list of running models
        running_models = await ollama_client.list_running_models()

        if not running_models:
            logger.info("No models currently running")
            return {
                "success": True,
                "message": "No models were running",
                "unloaded_models": []
            }

        model_names = [model.get("name", "unknown") for model in running_models]
        logger.info(f"Found {len(model_names)} running models: {model_names}")

        # Use httpx to send unload request to each model
        async with httpx.AsyncClient(timeout=30.0) as client:
            for model_info in running_models:
                model_name = model_info.get("name", "")
                if model_name:
                    try:
                        logger.info(f"Unloading model: {model_name}")
                        response = await client.post(
                            OLLAMA_GENERATE_ENDPOINT,
                            json={
                                "model": model_name,
                                "prompt": "",
                                "keep_alive": 0
                            }
                        )

                        if response.status_code == 200:
                            logger.info(f"Successfully unloaded: {model_name}")
                        else:
                            logger.warning(f"Unexpected response unloading {model_name}: {response.status_code}")

                    except Exception as model_error:
                        logger.error(f"Error unloading {model_name}: {model_error}")

        logger.info(f"Unloaded {len(model_names)} models")
        return {
            "success": True,
            "message": f"Unloaded {len(model_names)} model(s)",
            "unloaded_models": model_names
        }

    except Exception as e:
        logger.error(f"Error unloading models: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error unloading models: {str(e)}",
            "error": str(e)
        }


async def get_today_stats() -> Dict[str, Any]:
    """
    Get today's usage statistics.
    Currently returns mock data - will be wired up to real analytics later.

    Returns:
        Dict with today's stats:
        - sessions_count: Number of chat sessions today
        - total_tokens: Total tokens processed today
        - avg_ttft_ms: Average time to first token in milliseconds
        - agents_used: List of agent profiles used today
    """
    logger.info("Fetching today's stats (mock data)")

    # TODO: Wire up to real analytics database
    # For now, return mock data
    mock_stats = {
        "sessions_count": 42,
        "total_tokens": 15847,
        "avg_ttft_ms": 245,
        "agents_used": ["QWEN"],
        "is_mock": True  # Flag to indicate this is mock data
    }

    logger.info(f"Returning mock stats: {mock_stats}")
    return mock_stats
