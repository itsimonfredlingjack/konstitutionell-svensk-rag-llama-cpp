"""
REST API routes
Endpoints for profiles, GPU stats, health checks, and orchestrator status

Hybrid Orchestrator Pattern:
- /api/orchestrator/status - Provider status (Gemini + Ollama)
- /api/profiles - Available AI profiles (QWEN/GEMMA)
- /api/gpu/stats - GPU monitoring
"""

import uuid
import json
import os
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..models.Backend_Agent_Prompts import (
    get_all_profiles,
    get_profile,
    profile_manager,
    ProfileId,
    PROFILES,
)
from ..models.schemas import (
    ProfileInfo,
    ProfilesResponse,
    GPUStats,
    GPUStatsResponse,
    HealthResponse,
    OllamaStatus,
)
from ..services.ollama_client import OllamaClient, get_ollama_client
from ..services.gpu_monitor import GPUMonitor, get_gpu_monitor
from ..services.Backend_Fraga_Router import orchestrator
from ..services.intelligence import intelligence
from ..services.system_control import (
    warmup_model,
    restart_backend,
    restart_frontend,
    unload_all_models,
    get_today_stats,
)
from ..services.system_monitor import system_monitor
from ..services.shell_executor import shell_executor
from ..services.deploy_manager import deploy_manager
from .Backend_Chat_Stream import (
    emit_system_log,
    emit_mobile_activity,
    add_mobile_exchange,
    get_active_context,
    _pending_tool_confirmations,
    manager,  # WebSocket broadcast manager
)
from ..services.system_tools import system_tools, TOOLS, SafetyLevel
from ..config import settings
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    ollama: OllamaClient = Depends(get_ollama_client),
    gpu: GPUMonitor = Depends(get_gpu_monitor),
) -> HealthResponse:
    """
    Health check endpoint.
    Returns system status and component health.
    """
    # Check Ollama
    ollama_connected = await ollama.is_connected()
    ollama_version = await ollama.get_version() if ollama_connected else None
    models_available = await ollama.list_models() if ollama_connected else []
    running_models = await ollama.list_running_models() if ollama_connected else []

    # Check GPU
    gpu_available = await gpu.is_gpu_available()

    # Check required models (Generalist for local inference)
    generalist_model = PROFILES[ProfileId.GENERALIST].model
    generalist_available = generalist_model in models_available or any(generalist_model in m for m in models_available)

    # Determine overall status
    checks = {
        "ollama": ollama_connected,
        "gpu": gpu_available,
        "generalist_model": generalist_available,
    }

    # Healthy if Ollama works and generalist model is available
    if ollama_connected and generalist_available:
        status = "healthy"
    elif ollama_connected:
        status = "degraded"  # Ollama works but model missing
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        version=settings.app_version,
        timestamp=datetime.utcnow(),
        ollama=OllamaStatus(
            connected=ollama_connected,
            version=ollama_version,
            models_available=models_available,
            models_loaded=[m.get("name", "") for m in running_models],
        ),
        gpu_available=gpu_available,
        checks=checks,
    )


@router.get("/profiles", response_model=ProfilesResponse)
async def get_profiles() -> ProfilesResponse:
    """
    List available AI profiles (THINK/CHILL).
    Returns profile configurations and current status.
    """
    profiles = []
    active_profile = profile_manager.active_profile

    for profile in get_all_profiles():
        status = profile_manager.get_status(profile.id)
        profiles.append(ProfileInfo(
            id=profile.id.value,
            name=profile.name,
            display_name=profile.display_name,
            description=profile.description,
            model=profile.model,
            estimated_vram_gb=profile.estimated_vram_gb,
            icon=profile.icon,
            color=profile.color,
            strengths=profile.strengths or [],
            is_active=status.is_loaded,
            is_loading=status.is_loading,
        ))

    return ProfilesResponse(
        profiles=profiles,
        active_profile=active_profile.id.value if active_profile else None,
        default_profile=settings.default_profile,
    )


@router.get("/profiles/{profile_id}", response_model=ProfileInfo)
async def get_profile_by_id(profile_id: str) -> ProfileInfo:
    """
    Get a specific profile by ID.
    """
    try:
        pid = ProfileId(profile_id.lower())
        profile = PROFILES[pid]
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{profile_id}' not found. Available: qwen, gemma"
        )

    status = profile_manager.get_status(profile.id)

    return ProfileInfo(
        id=profile.id.value,
        name=profile.name,
        display_name=profile.display_name,
        description=profile.description,
        model=profile.model,
        estimated_vram_gb=profile.estimated_vram_gb,
        icon=profile.icon,
        color=profile.color,
        strengths=profile.strengths or [],
        is_active=status.is_loaded,
        is_loading=status.is_loading,
    )


@router.post("/profiles/{profile_id}/warmup")
async def warmup_profile(
    profile_id: str,
    ollama: OllamaClient = Depends(get_ollama_client),
) -> dict:
    """
    Pre-load a model into GPU memory.
    This reduces first-response latency.
    """
    try:
        pid = ProfileId(profile_id.lower())
        profile = PROFILES[pid]
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{profile_id}' not found"
        )

    logger.info(f"Warming up profile: {profile_id}")
    success = await ollama.warmup_model(profile)

    if not success:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to warm up model {profile.model}. Is Ollama running?"
        )

    return {
        "status": "ready",
        "profile": profile_id,
        "model": profile.model,
        "message": f"Model {profile.display_name} is now loaded and ready"
    }


@router.get("/gpu/stats", response_model=GPUStatsResponse)
async def get_gpu_stats(
    gpu: GPUMonitor = Depends(get_gpu_monitor),
    ollama: OllamaClient = Depends(get_ollama_client),
) -> GPUStatsResponse:
    """
    Get current GPU statistics.
    Used by frontend GPU monitor component.
    """
    stats = await gpu.get_stats()
    running = await ollama.list_running_models()

    return GPUStatsResponse(
        gpu=stats,
        timestamp=datetime.utcnow(),
        ollama_models_loaded=[m.get("name", "") for m in running],
    )


@router.get("/models")
async def list_models(
    ollama: OllamaClient = Depends(get_ollama_client),
) -> dict:
    """
    List all available Ollama models.
    """
    if not await ollama.is_connected():
        raise HTTPException(
            status_code=503,
            detail="Ollama not available. Start with: ollama serve"
        )

    models = await ollama.list_models()
    running = await ollama.list_running_models()

    return {
        "available": models,
        "loaded": [m.get("name", "") for m in running],
        "required": {
            "planner": PROFILES[ProfileId.CASCADE_PLANNER].model,
            "coder": PROFILES[ProfileId.CASCADE_CODER].model,
            "reviewer": PROFILES[ProfileId.CASCADE_REVIEWER].model,
        }
    }


@router.get("/orchestrator/status")
async def get_orchestrator_status() -> dict:
    """
    Get status of Hybrid Orchestrator providers.

    Returns status of:
    - xAI Grok (cloud) - for FAST mode
    - Ollama (local) - for DEEP mode
    """
    status = await orchestrator.get_status()
    return {
        "providers": status,
        "modes": {
            "auto": "Intelligent routing based on query",
            "fast": "Grok API (instant, cloud)",
            "deep": "Qwen 14B (max quality, local GPU)",
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# =============================================================================
# INTELLIGENCE ENDPOINTS
# =============================================================================

@router.get("/intelligence/project")
async def get_project_context(refresh: bool = False) -> dict:
    """
    Get project structure context for frontend display.

    Args:
        refresh: Force refresh of cached context
    """
    context = intelligence.get_project_context(force_refresh=refresh)
    return {
        "root_path": context.root_path,
        "file_tree": context.file_tree,
        "file_count": context.file_count,
        "directory_count": context.directory_count,
        "languages": context.languages_detected,
        "key_files": context.key_files,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.post("/intelligence/validate")
async def validate_code(body: dict) -> dict:
    """
    Validate code syntax (currently Python only).

    Body:
        code: str - Code to validate
        language: str - Language (default: python)
    """
    code = body.get("code", "")
    language = body.get("language", "python").lower()

    if language != "python":
        return {
            "valid": None,
            "supported": False,
            "message": f"Validation not supported for {language}. Only Python is supported."
        }

    from ..services.intelligence import validate_python_syntax, build_correction_prompt

    result = validate_python_syntax(code)

    response = {
        "valid": result.is_valid,
        "supported": True,
        "language": result.language
    }

    if not result.is_valid:
        response["error"] = {
            "message": result.error_message,
            "line": result.error_line
        }
        response["correction_prompt"] = build_correction_prompt(result)

    return response


@router.post("/intelligence/extract-json")
async def extract_json(body: dict) -> dict:
    """
    Extract and validate JSON from text.

    Body:
        text: str - Text containing JSON
        required_fields: list[str] - Optional required field names
    """
    text = body.get("text", "")
    required_fields = body.get("required_fields", [])

    from ..services.intelligence import extract_json_from_response, validate_json_against_schema

    success, data, raw = extract_json_from_response(text)

    response = {
        "found": success,
        "data": data if success else None,
        "raw": raw if success else None
    }

    if success and required_fields:
        valid, missing = validate_json_against_schema(data, required_fields)
        response["fields_valid"] = valid
        if not valid:
            response["missing_fields"] = missing

    if not success:
        response["error"] = data  # Contains error message

    return response


# =============================================================================
# KIOSK DASHBOARD CONTROL PANEL ENDPOINTS
# =============================================================================

@router.post("/warmup")
async def warmup_system() -> dict:
    """
    Warm up the system by pre-loading the default model.
    This reduces first-response latency.
    """
    try:
        logger.info("Kiosk Dashboard: Initiating system warmup")
        await emit_system_log("info", "System warmup initiated")

        result = await warmup_model()

        if result.get("success"):
            await emit_system_log("success", f"System warmup completed: {result.get('message', 'Model loaded')}")
            return {
                "success": True,
                "message": result.get("message", "Model warmed up successfully"),
                "model": result.get("model"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        else:
            await emit_system_log("error", f"System warmup failed: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "error": result.get("error", "Failed to warm up model"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    except Exception as e:
        error_msg = f"System warmup error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await emit_system_log("error", error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.post("/system/restart-backend")
async def restart_backend_service() -> dict:
    """
    Restart the backend service.
    This will reload all configurations and services.
    """
    try:
        logger.info("Kiosk Dashboard: Initiating backend restart")
        await emit_system_log("warning", "Backend restart initiated")

        result = await restart_backend()

        if result.get("success"):
            await emit_system_log("success", "Backend restart completed successfully")
            return {
                "success": True,
                "message": result.get("message", "Backend restart initiated"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        else:
            await emit_system_log("error", f"Backend restart failed: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "error": result.get("error", "Failed to restart backend"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    except Exception as e:
        error_msg = f"Backend restart error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await emit_system_log("error", error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.post("/system/restart-frontend")
async def restart_frontend_service() -> dict:
    """
    Restart the frontend service.
    This will reload the Next.js development server.
    """
    try:
        logger.info("Kiosk Dashboard: Initiating frontend restart")
        await emit_system_log("warning", "Frontend restart initiated")

        result = await restart_frontend()

        if result.get("success"):
            await emit_system_log("success", "Frontend restart completed successfully")
            return {
                "success": True,
                "message": result.get("message", "Frontend restart initiated"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        else:
            await emit_system_log("error", f"Frontend restart failed: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "error": result.get("error", "Failed to restart frontend"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    except Exception as e:
        error_msg = f"Frontend restart error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await emit_system_log("error", error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.post("/system/unload-models")
async def unload_models() -> dict:
    """
    Unload all models from GPU memory.
    This frees up VRAM and allows for model switching.
    """
    try:
        logger.info("Kiosk Dashboard: Initiating model unload")
        await emit_system_log("info", "Unloading all models from GPU memory")

        result = await unload_all_models()

        if result.get("success"):
            models_unloaded = result.get("models_unloaded", 0)
            await emit_system_log("success", f"Successfully unloaded {models_unloaded} model(s)")
            return {
                "success": True,
                "message": result.get("message", "All models unloaded"),
                "models_unloaded": models_unloaded,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        else:
            await emit_system_log("error", f"Model unload failed: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "error": result.get("error", "Failed to unload models"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    except Exception as e:
        error_msg = f"Model unload error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await emit_system_log("error", error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/stats/today")
async def get_stats_today() -> dict:
    """
    Get today's system statistics.
    Returns usage metrics, request counts, and performance data.
    """
    try:
        logger.info("Kiosk Dashboard: Fetching today's statistics")

        result = await get_today_stats()

        if result.get("success"):
            stats = result.get("stats", {})
            return {
                "success": True,
                "stats": stats,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        else:
            await emit_system_log("error", f"Failed to fetch stats: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "error": result.get("error", "Failed to retrieve statistics"),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    except Exception as e:
        error_msg = f"Stats retrieval error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await emit_system_log("error", error_msg)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


# =============================================================================
# MOBILE APP VOICE COMMAND ENDPOINT
# =============================================================================

@router.post("/voice-command")
async def voice_command(body: dict) -> dict:
    """
    Voice command endpoint for mobile app.
    Receives transcribed text and returns AI response.

    WAR ROOM SYNC: Broadcasts mobile_activity events to all connected dashboards.

    Request body:
        text: str - User message
        profile: str - Agent profile ("qwen", "nerdy", "gemma", default: "qwen")
    """
    text = body.get("text", "")
    profile = body.get("profile", "qwen").lower()

    if not text:
        return {"success": False, "error": "No text provided"}

    # Validate profile
    valid_profiles = ["qwen", "nerdy", "gemma"]
    if profile not in valid_profiles:
        profile = "qwen"

    try:
        # Skapa meddelande
        messages = [{"role": "user", "content": text}]
        request_id = str(uuid.uuid4())[:8]

        # WAR ROOM: Emit request start to dashboards
        await emit_mobile_activity("mobile_request_start", request_id, {
            "profile": profile,
            "question_preview": text[:50] + "..." if len(text) > 50 else text,
        })

        # Samla hela svaret från stream
        full_response = ""
        token_count = 0
        last_emit_time = datetime.utcnow()
        final_stats = None

        async for token, stats, agent_id in orchestrator.chat_stream(
            messages=messages,
            request_id=request_id,
            profile=profile,
        ):
            if token:
                full_response += token
                token_count += 1

            if stats:
                final_stats = stats

            # WAR ROOM: Emit generation progress every 500ms
            now = datetime.utcnow()
            if (now - last_emit_time).total_seconds() >= 0.5:
                tps = final_stats.tokens_per_second if final_stats else 0
                await emit_mobile_activity("mobile_generation", request_id, {
                    "tokens_generated": token_count,
                    "tokens_per_second": round(tps, 1),
                })
                last_emit_time = now

        # Build stats dict for response
        stats_dict = {}
        if final_stats:
            stats_dict = {
                "tokens_generated": final_stats.tokens_generated,
                "tokens_per_second": round(final_stats.tokens_per_second, 1),
                "total_duration_ms": final_stats.total_duration_ms,
            }

        # WAR ROOM: Add to active context buffer
        add_mobile_exchange(
            request_id=request_id,
            question=text,
            answer=full_response,
            profile=profile,
            stats=stats_dict,
        )

        # WAR ROOM: Emit complete response with active context
        await emit_mobile_activity("mobile_response", request_id, {
            "question": text,
            "answer": full_response[:300] + "..." if len(full_response) > 300 else full_response,
            "stats": stats_dict,
            "active_context": get_active_context(),
        })

        return {
            "success": True,
            "response": full_response or "Inget svar"
        }

    except Exception as e:
        logger.error(f"Voice command error: {e}")
        # WAR ROOM: Emit error
        await emit_mobile_activity("mobile_error", request_id, {
            "error": str(e)[:100],
        })
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/voice-command-stream")
async def voice_command_stream(body: dict) -> StreamingResponse:
    """
    SSE streaming endpoint for mobile app.
    Receives transcribed text and streams AI response token by token.

    Request body:
        text: str - User message
        profile: str - Agent profile ("qwen" or "nerdy", default: "qwen")
        history: list - Optional conversation history

    Response: Server-Sent Events stream
        - Each token: data: {"token": "..."}\n\n
        - On completion: data: {"done": true, "agent_id": "qwen"}\n\n
        - On error: data: {"error": "message"}\n\n
    """
    text = body.get("text", "")
    profile = body.get("profile", "qwen").lower()
    history = body.get("history", [])

    if not text:
        # Return immediate error response
        async def error_stream() -> AsyncGenerator[str, None]:
            error_data = {"error": "No text provided"}
            yield f"data: {json.dumps(error_data)}\n\n"

        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    # Validate profile
    valid_profiles = ["qwen", "nerdy", "gemma"]
    if profile not in valid_profiles:
        profile = "qwen"
        logger.warning(f"Invalid profile requested, defaulting to qwen. Valid: {valid_profiles}")

    async def event_stream() -> AsyncGenerator[str, None]:
        """Generate SSE stream from orchestrator"""
        try:
            # Build messages array with history
            messages = []

            # Add history if provided
            if history and isinstance(history, list):
                for msg in history:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })

            # Add current user message
            messages.append({"role": "user", "content": text})

            request_id = str(uuid.uuid4())[:8]
            logger.info(f"SSE stream started: request_id={request_id}, profile={profile}, messages={len(messages)}")

            # Stream tokens from orchestrator
            agent_id = profile
            async for token, stats, returned_agent_id in orchestrator.chat_stream(
                messages=messages,
                request_id=request_id,
                profile=profile,
            ):
                if returned_agent_id:
                    agent_id = returned_agent_id

                if token:
                    token_data = {"token": token}
                    yield f"data: {json.dumps(token_data)}\n\n"

            # Send completion event
            completion_data = {
                "done": True,
                "agent_id": agent_id
            }
            yield f"data: {json.dumps(completion_data)}\n\n"

            logger.info(f"SSE stream completed: request_id={request_id}, agent_id={agent_id}")

        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            error_data = {"error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# =============================================================================
# MOBILE APP ADMIN ENDPOINTS - System Health, Shell, Deploy
# =============================================================================

@router.get("/system/health")
async def get_system_health() -> dict:
    """
    Get complete system health statistics.
    Returns CPU, RAM, Disk, GPU stats for the admin dashboard.
    """
    try:
        stats = await system_monitor.get_stats()
        return {
            "success": True,
            **stats.to_dict()
        }
    except Exception as e:
        logger.error(f"System health error: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/system/health/quick")
async def get_system_health_quick() -> dict:
    """
    Get minimal system health for frequent polling.
    Returns just percentages for CPU, RAM, Disk, GPU.
    """
    try:
        summary = await system_monitor.get_quick_summary()
        return {
            "success": True,
            **summary,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Quick health error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/shell/execute")
async def execute_shell_command(body: dict) -> dict:
    """
    Execute a shell command.

    WAR ROOM SYNC: Broadcasts mobile_shell event to dashboards.

    Request body:
        command: str - Command to execute (with or without $ prefix)
        confirmed: bool - Whether dangerous commands are confirmed

    Response:
        success, stdout, stderr, exit_code, duration_ms
    """
    command = body.get("command", "")
    confirmed = body.get("confirmed", False)

    if not command:
        return {
            "success": False,
            "error": "No command provided",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    try:
        result = await shell_executor.execute(command, confirmed=confirmed)
        result_dict = result.to_dict()

        # WAR ROOM: Emit shell command to dashboards
        shell_id = f"shell_{datetime.utcnow().strftime('%H%M%S')}"
        await emit_mobile_activity("mobile_shell", shell_id, {
            "command": command[:80],
            "stdout": result_dict.get("stdout", "")[:500],
            "exit_code": result_dict.get("exit_code", -1),
            "success": result_dict.get("success", False),
        })

        return result_dict
    except Exception as e:
        logger.error(f"Shell execute error: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/shell/commands")
async def get_shell_commands() -> dict:
    """
    Get list of quick commands for the UI.
    Returns predefined safe commands for easy access.
    """
    try:
        commands = await shell_executor.get_quick_commands()
        return {
            "success": True,
            "commands": commands
        }
    except Exception as e:
        logger.error(f"Get commands error: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# QWEN SYSADMIN TOOLS - Tool Execution Endpoints
# =============================================================================

@router.get("/tools")
async def list_tools() -> dict:
    """
    List all available QWEN SysAdmin tools.
    Returns tool definitions with safety levels.
    """
    tools_list = []
    for name, tool_def in TOOLS.items():
        tools_list.append({
            "name": name,
            "description": tool_def.description,
            "safety": tool_def.safety.value,
            "params": tool_def.params,
        })

    return {
        "success": True,
        "tools": tools_list,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.post("/tools/execute")
async def execute_tool(body: dict) -> dict:
    """
    Execute a QWEN SysAdmin tool.

    This endpoint is used for:
    1. Confirming and executing DANGEROUS tools after user approval
    2. Directly executing tools from admin interface

    Request body:
        tool: str - Tool name (e.g., "docker_restart")
        params: dict - Tool parameters
        confirmed: bool - Whether user has confirmed (required for DANGEROUS tools)
        request_id: str - Optional request ID for pending confirmations

    Response:
        success, output, error
    """
    tool_name = body.get("tool", "")
    params = body.get("params", {})
    confirmed = body.get("confirmed", False)
    request_id = body.get("request_id")

    if not tool_name:
        return {
            "success": False,
            "error": "No tool specified",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    # Check if tool exists
    tool_def = TOOLS.get(tool_name)
    if not tool_def:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}. Use GET /api/tools for available tools.",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    # Check safety level
    if tool_def.safety == SafetyLevel.DANGEROUS and not confirmed:
        return {
            "success": False,
            "error": f"Tool '{tool_name}' is DANGEROUS and requires confirmation. Set confirmed=true.",
            "requires_confirmation": True,
            "tool": tool_name,
            "description": tool_def.description,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    # If this is a pending confirmation, remove it from pending
    if request_id and request_id in _pending_tool_confirmations:
        pending = _pending_tool_confirmations.pop(request_id)
        # Use params from pending if not overridden
        if not params:
            params = pending.get("params", {})

    try:
        await emit_system_log(
            "tool_execute",
            f"[SYSTEM] Executing {tool_name}...",
            "info",
            "qwen"
        )

        # Execute the tool
        result = await system_tools.execute(tool_name, params)

        # Log result
        if result.success:
            await emit_system_log(
                "tool_success",
                f"[SYSTEM] {tool_name}: OK",
                "success",
                "qwen"
            )
        else:
            await emit_system_log(
                "tool_error",
                f"[SYSTEM] {tool_name}: {result.error}",
                "error",
                "qwen"
            )

        return {
            "success": result.success,
            "tool": tool_name,
            "output": result.output,
            "error": result.error,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        error_msg = f"Tool execution error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await emit_system_log("tool_error", error_msg, "error", "qwen")
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.post("/tools/confirm/{request_id}")
async def confirm_tool(request_id: str) -> dict:
    """
    Confirm and execute a pending DANGEROUS tool.

    This is called when user clicks "Godkänn" in the frontend after
    QWEN requests a dangerous operation.

    Path params:
        request_id: The request_id from confirmation_required message
    """
    if request_id not in _pending_tool_confirmations:
        return {
            "success": False,
            "error": f"No pending tool confirmation for request_id: {request_id}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    pending = _pending_tool_confirmations.pop(request_id)
    tool_name = pending["tool"]
    params = pending["params"]

    await emit_system_log(
        "tool_confirmed",
        f"[USER] Confirmed: {tool_name}",
        "warn",
        "qwen"
    )

    try:
        result = await system_tools.execute(tool_name, params)

        if result.success:
            await emit_system_log(
                "tool_success",
                f"[SYSTEM] {tool_name}: OK",
                "success",
                "qwen"
            )
        else:
            await emit_system_log(
                "tool_error",
                f"[SYSTEM] {tool_name}: {result.error}",
                "error",
                "qwen"
            )

        return {
            "success": result.success,
            "tool": tool_name,
            "output": result.output,
            "error": result.error,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        error_msg = f"Tool execution error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.post("/tools/cancel/{request_id}")
async def cancel_tool(request_id: str) -> dict:
    """
    Cancel a pending DANGEROUS tool.

    This is called when user clicks "Avbryt" in the frontend.
    """
    if request_id not in _pending_tool_confirmations:
        return {
            "success": False,
            "error": f"No pending tool confirmation for request_id: {request_id}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    pending = _pending_tool_confirmations.pop(request_id)
    tool_name = pending["tool"]

    await emit_system_log(
        "tool_cancelled",
        f"[USER] Cancelled: {tool_name}",
        "warn",
        "qwen"
    )

    return {
        "success": True,
        "message": f"Tool {tool_name} cancelled",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.post("/deploy/git-pull")
async def deploy_git_pull() -> dict:
    """
    Pull latest changes from git repository.
    Uses --ff-only to prevent merge conflicts.
    """
    try:
        await emit_system_log("info", "Git pull initiated from mobile app")
        result = await deploy_manager.git_pull()

        if result.success:
            await emit_system_log("success", f"Git pull completed: {result.output}")
        else:
            await emit_system_log("error", f"Git pull failed: {result.error}")

        return result.to_dict()
    except Exception as e:
        logger.error(f"Git pull error: {e}")
        return {
            "success": False,
            "operation": "git_pull",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/deploy/git-status")
async def deploy_git_status() -> dict:
    """Get current git status (modified files, etc.)"""
    try:
        result = await deploy_manager.git_status()
        return result.to_dict()
    except Exception as e:
        logger.error(f"Git status error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/deploy/restart/{service}")
async def deploy_restart_service(service: str, body: dict = None) -> dict:
    """
    Restart a systemd service.

    Path params:
        service: "simons-ai-backend", "simons-ai-frontend", or "ollama"
    """
    try:
        await emit_system_log("warning", f"Service restart initiated: {service}")
        result = await deploy_manager.restart_service(service)

        if result.success:
            await emit_system_log("success", f"Service {service} restarted")
        else:
            await emit_system_log("error", f"Failed to restart {service}: {result.error}")

        return result.to_dict()
    except Exception as e:
        logger.error(f"Restart service error: {e}")
        return {
            "success": False,
            "operation": f"restart_{service}",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/deploy/status/{service}")
async def deploy_service_status(service: str) -> dict:
    """
    Get status of a systemd service.

    Path params:
        service: "simons-ai-backend", "simons-ai-frontend", or "ollama"
    """
    try:
        result = await deploy_manager.get_service_status(service)
        return result.to_dict()
    except Exception as e:
        logger.error(f"Service status error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/deploy/full")
async def deploy_full() -> StreamingResponse:
    """
    Full deployment: git pull + restart backend + restart frontend.

    Returns Server-Sent Events with progress updates.
    """
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            await emit_system_log("warning", "Full deploy initiated from mobile app")

            async for progress in deploy_manager.full_deploy():
                data = {
                    "step": progress.step,
                    "status": progress.status,
                    "message": progress.message,
                    "output": progress.output,
                }
                yield f"data: {json.dumps(data)}\n\n"

            await emit_system_log("success", "Full deploy completed")

        except Exception as e:
            logger.error(f"Full deploy error: {e}")
            error_data = {"step": "error", "status": "failed", "message": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# =============================================================================
# APK DOWNLOAD ENDPOINT
# =============================================================================

@router.get("/download/apk")
async def download_apk():
    """
    Serve the Android APK file with proper headers for download.
    Uses StreamingResponse to handle the 72MB file efficiently.
    """
    apk_path = Path("/home/ai-server/simons-ai-v2-nerdy-fix.apk")

    if not apk_path.exists():
        raise HTTPException(status_code=404, detail="APK file not found")

    file_size = os.path.getsize(apk_path)

    async def file_iterator():
        """Stream the file in chunks to avoid loading it all into memory"""
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(apk_path, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": f"attachment; filename={apk_path.name}",
            "Content-Length": str(file_size),
            "Cache-Control": "no-cache",
        }
    )


# =============================================================================
# LIVE PREVIEW ENDPOINT - Claude Code Design Preview
# =============================================================================

@router.post("/preview")
async def receive_preview(body: dict) -> dict:
    """
    Receive code preview from Claude Code (via MCP or terminal).
    Broadcasts to all connected frontend clients via WebSocket.

    Request body:
        code: str - HTML or React code to preview
        code_type: str - "html" or "react" (default: "html")
        title: str - Optional title for the preview

    WebSocket broadcast:
        type: "preview_update"
        code: str
        code_type: str
        title: str
    """
    code = body.get("code", "")
    code_type = body.get("code_type", "html")
    title = body.get("title", "Preview")

    if not code:
        return {
            "success": False,
            "error": "No code provided",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    # Validate code_type
    if code_type not in ["html", "react"]:
        code_type = "html"

    # Broadcast to all connected WebSocket clients
    preview_packet = {
        "type": "preview_update",
        "code": code,
        "code_type": code_type,
        "title": title,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    await manager.broadcast(preview_packet)
    await emit_system_log(
        "preview",
        f"[PREVIEW] {title} ({code_type}) - {len(code)} chars",
        "info"
    )

    logger.info(f"Preview broadcast: {title} ({code_type}, {len(code)} chars)")

    return {
        "success": True,
        "message": f"Preview '{title}' broadcast to {len(manager.active_connections)} clients",
        "code_type": code_type,
        "code_length": len(code),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
