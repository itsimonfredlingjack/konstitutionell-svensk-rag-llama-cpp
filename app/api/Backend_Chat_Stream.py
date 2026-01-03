"""
WebSocket endpoint for streaming chat
Handles real-time communication with frontend

SVEN DUAL-EXPERT SYSTEM:
- GPT-OSS 20B: Arkitekten (GPT-OSS 20B via Ollama) - Planering & Reasoning
- Devstral 24B: Kodaren (Devstral 24B via Ollama) - Implementation
- NERDY: Legal/Compliance (qwen2.5:3b-instruct)

Frontend sends `profile` ID → Backend routes to correct model + prompt.
Each response includes `agent_id` for panel highlighting.

OPERATION VITAL SIGNS Features:
- Real-time GPU telemetry broadcast (every 2 seconds)
- Dynamic agent highlighting via agent_id
- Latency tracking (TTFT - Time To First Token)
"""

import json
import asyncio
import uuid
import time
import re
from typing import Optional
from dataclasses import dataclass, field
from collections import deque
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

from ..models.Backend_Agent_Prompts import get_profile, profile_manager
from ..services.system_tools import system_tools, TOOLS, SafetyLevel
from ..models.schemas import (
    ChatRequest,
    ChatMessage,
    ChatStats,
    WSMessageType,
)
from ..services.Backend_Fraga_Router import orchestrator, get_agent, AGENTS, AgentId
from ..services.ollama_client import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaError,
    ollama_client,
)
from ..services.gpu_monitor import gpu_monitor
from ..utils.logging import get_logger, RequestLogger

logger = get_logger(__name__)

# GPU Telemetry broadcast settings
GPU_BROADCAST_INTERVAL = 1.0  # seconds (1s for responsive meters)
_gpu_broadcast_task: Optional[asyncio.Task] = None
_status_pulse_task: Optional[asyncio.Task] = None

# System log buffer for terminal display
_system_logs: list[dict] = []
MAX_LOG_BUFFER = 50  # Keep last 50 log entries

# Status pulse interval (seconds) - periodic health checks
STATUS_PULSE_INTERVAL = 30.0

# =============================================================================
# TOOL CALL PARSING - QWEN SYSADMIN TOOLS
# =============================================================================

# Pattern to detect JSON tool calls in QWEN responses
TOOL_JSON_PATTERN = re.compile(
    r'\{[^{}]*"tool"\s*:\s*"[^"]+"\s*[^{}]*\}',
    re.DOTALL
)


def extract_tool_call(text: str) -> Optional[dict]:
    """
    Extract JSON tool call from QWEN's response text.

    QWEN will include tool calls like:
        {"tool": "docker_ps"}
        {"tool": "docker_logs", "container": "nginx", "lines": 50}

    Returns:
        dict with tool name and params, or None if no tool call found
    """
    match = TOOL_JSON_PATTERN.search(text)
    if not match:
        return None

    try:
        data = json.loads(match.group())
        if "tool" in data:
            return data
    except json.JSONDecodeError:
        pass

    return None


# Pending tool confirmations (request_id -> tool call data)
_pending_tool_confirmations: dict[str, dict] = {}


# =============================================================================
# MOBILE ACTIVITY BROADCAST - WAR ROOM SYNC
# =============================================================================

@dataclass
class MobileExchange:
    """Represents a mobile Q&A exchange for the Active Context buffer"""
    request_id: str
    question: str
    answer: str
    profile: str
    timestamp: str
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "question": self.question[:100] + "..." if len(self.question) > 100 else self.question,
            "answer": self.answer[:200] + "..." if len(self.answer) > 200 else self.answer,
            "profile": self.profile,
            "timestamp": self.timestamp,
            "stats": self.stats,
        }


# Active Context buffer - stores last 3 Q&A exchanges from mobile
_mobile_context: deque[MobileExchange] = deque(maxlen=3)


def get_active_context() -> list[dict]:
    """Returns last 3 Q&A exchanges for dashboard display"""
    return [ex.to_dict() for ex in reversed(_mobile_context)]


def add_mobile_exchange(
    request_id: str,
    question: str,
    answer: str,
    profile: str,
    stats: dict = None
) -> None:
    """Add a completed Q&A exchange to the active context buffer"""
    exchange = MobileExchange(
        request_id=request_id,
        question=question,
        answer=answer,
        profile=profile,
        timestamp=datetime.utcnow().isoformat() + "Z",
        stats=stats or {},
    )
    _mobile_context.append(exchange)


async def emit_mobile_activity(
    event_type: str,
    request_id: str,
    data: dict
) -> None:
    """
    Broadcast mobile activity to all connected dashboard clients.

    Event types:
    - mobile_request_start: Mobile request initiated
    - mobile_generation: Token generation progress
    - mobile_response: Complete Q&A response
    - mobile_shell: Shell command executed
    """
    packet = {
        "type": "mobile_activity",
        "event": event_type,
        "request_id": request_id,
        "source": "mobile",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **data
    }
    await manager.broadcast(packet)
    logger.debug(f"Mobile activity broadcast: {event_type} ({request_id})")


async def emit_war_room_event(
    event_type: str,
    data: dict
) -> None:
    """
    Broadcast War Room events to all dashboard clients for real-time sync.

    Event types:
    - start: Mobile/WebSocket request initiated (shows user prompt)
    - stream: Batched tokens (100ms intervals for smooth display)
    - end: Response complete (shows stats)

    Used by KioskDashboard to display mobile sessions in real-time.
    """
    packet = {
        "type": "war_room_event",
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **data
    }
    await manager.broadcast(packet)
    logger.debug(f"War Room broadcast: {event_type}")


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    async def send_json(self, websocket: WebSocket, data: dict) -> None:
        """Send JSON message to a specific connection"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def broadcast(self, data: dict) -> None:
        """Broadcast message to all connections"""
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                pass


# Global connection manager
manager = ConnectionManager()


# =============================================================================
# SYSTEM LOG BROADCAST - Terminal feed for hacker aesthetic
# =============================================================================

async def emit_system_log(
    event: str,
    message: str,
    level: str = "info",
    agent_id: str | None = None
) -> None:
    """
    Emit a system log event to all connected clients.

    Args:
        event: Event type (e.g., 'model_load', 'generation_start', 'error')
        message: Human-readable log message
        level: Log level ('info', 'warn', 'error', 'success')
        agent_id: Optional agent that triggered this log
    """
    global _system_logs

    log_entry = {
        "type": "system_log",
        "event": event,
        "message": message,
        "level": level,
        "agent_id": agent_id,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    # Add to buffer (circular)
    _system_logs.append(log_entry)
    if len(_system_logs) > MAX_LOG_BUFFER:
        _system_logs = _system_logs[-MAX_LOG_BUFFER:]

    # Broadcast to all connections
    await manager.broadcast(log_entry)


def get_recent_logs(count: int = 20) -> list[dict]:
    """Get recent system logs for new connections"""
    return _system_logs[-count:]


# =============================================================================
# GPU TELEMETRY BROADCAST - Real-time system monitoring
# =============================================================================

async def gpu_telemetry_loop():
    """
    Background task that broadcasts GPU stats to all connected clients.
    Runs every GPU_BROADCAST_INTERVAL seconds.

    Sends status_update packets with:
    - GPU VRAM usage, temperature, utilization
    - Number of active models in Ollama
    """
    logger.info("GPU telemetry broadcast started")

    while True:
        try:
            await asyncio.sleep(GPU_BROADCAST_INTERVAL)

            # Skip if no connections
            if not manager.active_connections:
                continue

            # Fetch GPU stats
            gpu_stats = await gpu_monitor.get_stats()

            # Fetch active models count
            running_models = await ollama_client.list_running_models()
            active_models_count = len(running_models)

            # Build status_update packet (matches frontend expectations)
            status_packet = {
                "type": "status_update",
                "gpu": {
                    "vram_used_gb": round(gpu_stats.vram_used_gb, 2),
                    "vram_total_gb": round(gpu_stats.vram_total_gb, 2),
                    "vram_percent": round(gpu_stats.vram_percent, 1),
                    "temperature_c": gpu_stats.temperature_c,
                    "utilization_percent": gpu_stats.gpu_util_percent,
                    "power_draw_w": gpu_stats.power_draw_w,
                    "power_limit_w": gpu_stats.power_limit_w,
                    "name": gpu_stats.name,
                    "is_available": gpu_stats.is_available,
                },
                "active_models_count": active_models_count,
                "active_models": [m.get("name", "") for m in running_models],
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

            # Broadcast to all connections
            await manager.broadcast(status_packet)

        except asyncio.CancelledError:
            logger.info("GPU telemetry broadcast stopped")
            break
        except Exception as e:
            logger.error(f"GPU telemetry error: {e}")
            # Continue loop despite errors
            await asyncio.sleep(GPU_BROADCAST_INTERVAL)


def start_gpu_broadcast():
    """Start the GPU telemetry background task"""
    global _gpu_broadcast_task
    if _gpu_broadcast_task is None or _gpu_broadcast_task.done():
        _gpu_broadcast_task = asyncio.create_task(gpu_telemetry_loop())
        logger.info("GPU telemetry broadcast task created")


def stop_gpu_broadcast():
    """Stop the GPU telemetry background task"""
    global _gpu_broadcast_task
    if _gpu_broadcast_task and not _gpu_broadcast_task.done():
        _gpu_broadcast_task.cancel()
        logger.info("GPU telemetry broadcast task cancelled")


# =============================================================================
# STATUS PULSE - Periodic health messages for Kiosk dashboard
# =============================================================================

async def status_pulse_loop():
    """
    Background task that emits periodic status messages.
    Makes the Kiosk dashboard feel alive even when idle.
    """
    import random

    pulse_messages = [
        ("System operativt", "success"),
        ("Alla agenter redo", "success"),
        ("GPU temp stabil", "info"),
        ("Väntar på förfrågan...", "info"),
        ("Ollama ansluten", "success"),
        ("WebSocket aktiv", "info"),
    ]

    # Initial boot sequence
    boot_sequence = [
        ("SIMONS AI initieras...", "info"),
        ("Laddar agenter: QN3, DeepSeek, DS Mini", "info"),
        ("GPU-övervakning aktiv", "success"),
        ("System redo för förfrågningar", "success"),
    ]

    first_run = True

    while True:
        try:
            if not manager.active_connections:
                await asyncio.sleep(STATUS_PULSE_INTERVAL)
                continue

            if first_run:
                # Send boot sequence on first connection
                for msg, level in boot_sequence:
                    await emit_system_log("boot", msg, level)
                    await asyncio.sleep(0.5)
                first_run = False
            else:
                # Random pulse message
                msg, level = random.choice(pulse_messages)
                await emit_system_log("pulse", msg, level)

            await asyncio.sleep(STATUS_PULSE_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Status pulse stopped")
            break
        except Exception as e:
            logger.error(f"Status pulse error: {e}")
            await asyncio.sleep(STATUS_PULSE_INTERVAL)


def start_status_pulse():
    """Start the status pulse background task"""
    global _status_pulse_task
    if _status_pulse_task is None or _status_pulse_task.done():
        _status_pulse_task = asyncio.create_task(status_pulse_loop())
        logger.info("Status pulse task created")


def stop_status_pulse():
    """Stop the status pulse background task"""
    global _status_pulse_task
    if _status_pulse_task and not _status_pulse_task.done():
        _status_pulse_task.cancel()
        logger.info("Status pulse task cancelled")


async def send_error(
    websocket: WebSocket,
    request_id: str,
    code: str,
    message: str,
    retry_after_ms: Optional[int] = None
) -> None:
    """Send error message to client"""
    await manager.send_json(websocket, {
        "type": WSMessageType.ERROR.value,
        "request_id": request_id,
        "code": code,
        "message": message,
        "retry_after_ms": retry_after_ms,
    })


async def send_warmup(
    websocket: WebSocket,
    request_id: str,
    model: str,
    status: str,
    progress: Optional[int] = None
) -> None:
    """Send model warmup status"""
    await manager.send_json(websocket, {
        "type": WSMessageType.WARMUP.value,
        "request_id": request_id,
        "model": model,
        "status": status,
        "progress_percent": progress,
    })


async def handle_chat_message(
    websocket: WebSocket,
    data: dict
) -> None:
    """
    Handle incoming chat request with streaming response.
    Uses 4-Agent Orchestrator for profile-based routing.

    Frontend sends profile: qwen/gemma/cloud/nerdy
    Backend routes to correct model with appropriate system prompt.
    Every packet includes agent_id for frontend panel highlighting.
    """
    # Parse request
    try:
        request = ChatRequest(**data)
    except Exception as e:
        logger.error(f"Invalid chat request: {e}")
        await send_error(
            websocket,
            data.get("request_id", "unknown"),
            "INVALID_REQUEST",
            f"Invalid request format: {str(e)}"
        )
        return

    # Get agent config for display info
    agent = get_agent(request.profile)

    req_logger = RequestLogger(logger, request.request_id, profile=request.profile)
    req_logger.info(f"Chat request - profile: {request.profile} → agent: {agent.display_name}")

    # Build messages list
    messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

    # Start timing for latency tracking
    request_start_time = time.time()
    first_token_sent = False
    latency_ms = None

    # Send start message with agent_id for highlighting
    await manager.send_json(websocket, {
        "type": WSMessageType.START.value,
        "request_id": request.request_id,
        "profile": request.profile,
        "agent_id": agent.id.value,  # For panel highlighting
        "model": agent.model,
        "sender": "agent",
    })

    try:
        # Stream response via 4-agent orchestrator
        final_stats = None
        token_count = 0
        active_agent_id = agent.id.value

        async for token, stats, agent_id in orchestrator.chat_stream(
            messages=messages,
            request_id=request.request_id,
            profile=request.profile,  # Route by profile, not mode
            temperature=None,  # Use agent's default
            max_tokens=4096
        ):
            active_agent_id = agent_id

            if token:
                token_count += 1

                # Calculate latency on first token
                if not first_token_sent:
                    latency_ms = int((time.time() - request_start_time) * 1000)
                    first_token_sent = True
                    req_logger.info(f"TTFT: {latency_ms}ms")

                # Send token with agent_id for highlighting
                token_packet = {
                    "type": WSMessageType.TOKEN.value,
                    "content": token,
                    "request_id": request.request_id,
                    "agent_id": active_agent_id,  # For panel highlighting
                    "sender": "agent",
                    "text": token,  # Antigravity format compatibility
                    "is_finished": False,
                }

                # Include latency only on first token
                if latency_ms is not None:
                    token_packet["latency_ms"] = latency_ms
                    latency_ms = None  # Only send once

                await manager.send_json(websocket, token_packet)

            if stats:
                final_stats = stats

        # Send completion with full stats and agent_id
        done_packet = {
            "type": WSMessageType.DONE.value,
            "request_id": request.request_id,
            "agent_id": final_stats.agent_id if final_stats else active_agent_id,
            "sender": "agent",
            "text": "",
            "is_finished": True,
            "model": final_stats.model if final_stats else agent.model,
            "provider": final_stats.provider if final_stats else agent.provider.value,
        }

        if final_stats:
            done_packet["stats"] = {
                "tokens_generated": final_stats.tokens_generated,
                "tokens_per_second": round(final_stats.tokens_per_second, 1),
                "total_duration_ms": final_stats.total_duration_ms,
                "prompt_tokens": final_stats.prompt_tokens,
                "model": final_stats.model,
                "provider": final_stats.provider,
                "agent_id": final_stats.agent_id,
                "profile": request.profile,
            }

        await manager.send_json(websocket, done_packet)

        req_logger.info(
            f"Completed via {active_agent_id}: {token_count} tokens "
            f"in {final_stats.total_duration_ms if final_stats else 0}ms"
        )

    except OllamaConnectionError as e:
        req_logger.error(f"Connection error: {e}")
        await send_error(
            websocket,
            request.request_id,
            "PROVIDER_DISCONNECTED",
            str(e),
            retry_after_ms=5000
        )

    except OllamaModelNotFoundError as e:
        req_logger.error(f"Model not found: {e}")
        await send_error(
            websocket,
            request.request_id,
            "MODEL_NOT_FOUND",
            str(e)
        )

    except OllamaTimeoutError as e:
        req_logger.error(f"Timeout: {e}")
        await send_error(
            websocket,
            request.request_id,
            "TIMEOUT",
            str(e),
            retry_after_ms=10000
        )

    except Exception as e:
        req_logger.error(f"Unexpected error: {e}")
        await send_error(
            websocket,
            request.request_id,
            "INTERNAL_ERROR",
            f"An unexpected error occurred: {str(e)}"
        )


async def handle_ping(websocket: WebSocket, data: dict) -> None:
    """Handle ping message"""
    await manager.send_json(websocket, {
        "type": WSMessageType.PONG.value,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


async def handle_switch_profile(websocket: WebSocket, data: dict) -> None:
    """Handle profile switch request"""
    profile_id = data.get("profile", "chill")
    profile = get_profile(profile_id)

    # Optionally warmup the model
    if data.get("warmup", False):
        await send_warmup(websocket, "switch", profile.model, "loading")
        success = await ollama_client.warmup_model(profile)
        status = "ready" if success else "failed"
        await send_warmup(websocket, "switch", profile.model, status)

    await manager.send_json(websocket, {
        "type": WSMessageType.PROFILE_CHANGED.value,
        "profile": profile.id.value,
        "display_name": profile.display_name,
        "model": profile.model,
    })


async def handle_antigravity_message(websocket: WebSocket, data: dict) -> None:
    """
    Handle Antigravity/Robot Unicorn frontend protocol (legacy simple format).

    Incoming format:
        {"text": "user message", "profile": "qwen"|"gemma"|"cloud"|"nerdy"}

    Outgoing format (streamed):
        {"sender": "agent", "text": "token...", "is_finished": false, "agent_id": "qwen"}
        {"sender": "agent", "text": "", "is_finished": true, "stats": {...}}

    OPERATION VITAL SIGNS features:
        - agent_id: Identifies which agent panel should highlight
        - latency_ms: Time to first token (TTFT), sent with first token
    """
    text = data.get("text", "")
    profile = data.get("profile", "cascade-planner")

    if not text:
        await manager.send_json(websocket, {
            "sender": "agent",
            "text": "Error: No text provided",
            "is_finished": True,
            "error": True
        })
        return

    request_id = str(uuid.uuid4())
    agent = get_agent(profile)
    logger.info(f"[{request_id}] Antigravity request - profile: {profile} → {agent.display_name}")

    # Emit system log for terminal
    await emit_system_log(
        "request_start",
        f"[{agent.display_name}] Processing request...",
        "info",
        agent.id.value
    )

    # Build messages list (simple format - just the user message)
    messages = [{"role": "user", "content": text}]

    # Start timing for latency tracking
    request_start_time = time.time()
    first_token_sent = False

    # WAR ROOM: Broadcast request start to all dashboards
    await emit_war_room_event("start", {
        "agent": profile,
        "user_prompt": text[:100],
        "request_id": request_id,
    })

    try:
        # Stream response via 4-agent orchestrator
        full_response = []
        final_stats = None
        active_agent_id = agent.id.value
        latency_ms = None

        # WAR ROOM: 100ms token batching for smooth dashboard display
        war_room_buffer = []
        last_war_room_flush = time.time()
        WAR_ROOM_FLUSH_INTERVAL = 0.1  # 100ms
        WAR_ROOM_BUFFER_MAX = 50  # chars

        async for token, stats, agent_id in orchestrator.chat_stream(
            messages=messages,
            request_id=request_id,
            profile=profile
        ):
            active_agent_id = agent_id

            if token:
                full_response.append(token)

                # Calculate latency on first token
                if not first_token_sent:
                    latency_ms = int((time.time() - request_start_time) * 1000)
                    first_token_sent = True
                    logger.info(f"[{request_id}] TTFT: {latency_ms}ms via {agent_id}")

                    # Emit system log for TTFT
                    await emit_system_log(
                        "generation_start",
                        f"[{agent.display_name}] Streaming response (TTFT: {latency_ms}ms)",
                        "success",
                        agent_id
                    )

                # Stream each token to frontend with agent_id and latency
                token_packet = {
                    "sender": "agent",
                    "text": token,
                    "is_finished": False,
                    "model": agent.model,
                    "provider": agent.provider.value,
                    "agent_id": active_agent_id,  # For dynamic highlighting
                }

                # Include latency only on first token
                if latency_ms is not None:
                    token_packet["latency_ms"] = latency_ms
                    latency_ms = None  # Only send once

                await manager.send_json(websocket, token_packet)

                # WAR ROOM: Add token to buffer
                war_room_buffer.append(token)
                buffer_text = "".join(war_room_buffer)
                now = time.time()

                # Flush if 100ms elapsed OR buffer > 50 chars
                if (now - last_war_room_flush >= WAR_ROOM_FLUSH_INTERVAL) or len(buffer_text) > WAR_ROOM_BUFFER_MAX:
                    await emit_war_room_event("stream", {
                        "tokens": buffer_text,
                        "request_id": request_id,
                    })
                    war_room_buffer = []
                    last_war_room_flush = now

            if stats:
                final_stats = stats

        # WAR ROOM: Flush any remaining tokens in buffer
        if war_room_buffer:
            await emit_war_room_event("stream", {
                "tokens": "".join(war_room_buffer),
                "request_id": request_id,
            })

        # WAR ROOM: Broadcast completion with stats
        duration_ms = int((time.time() - request_start_time) * 1000)
        await emit_war_room_event("end", {
            "request_id": request_id,
            "stats": {
                "tokens": len(full_response),
                "duration_ms": duration_ms,
            }
        })

        # =================================================================
        # TOOL CALL DETECTION - Check if QWEN wants to run a tool
        # =================================================================
        full_text = "".join(full_response)
        tool_call = extract_tool_call(full_text)

        if tool_call and profile == "qwen":
            tool_name = tool_call.get("tool")
            params = {k: v for k, v in tool_call.items() if k != "tool"}

            tool_def = TOOLS.get(tool_name)

            if tool_def:
                logger.info(f"[{request_id}] Tool call detected: {tool_name} ({tool_def.safety.value})")

                await emit_system_log(
                    "tool_call",
                    f"[QWEN] Verktygsanrop: {tool_name}",
                    "info",
                    "qwen"
                )

                if tool_def.safety == SafetyLevel.SAFE:
                    # Execute SAFE tool directly
                    result = await system_tools.execute(tool_name, params)

                    # Send tool result to frontend
                    await manager.send_json(websocket, {
                        "sender": "system",
                        "tool_result": {
                            "tool": tool_name,
                            "success": result.success,
                            "output": result.output[:2000] if result.output else "",
                            "error": result.error,
                        },
                        "is_finished": False
                    })

                    await emit_system_log(
                        "tool_executed",
                        f"[SYSTEM] {tool_name}: {'OK' if result.success else 'FEL'}",
                        "success" if result.success else "error",
                        "qwen"
                    )

                    # Let QWEN interpret the result
                    follow_up_messages = [
                        {"role": "user", "content": text},
                        {"role": "assistant", "content": full_text},
                        {"role": "user", "content": f"Verktygsresultat för {tool_name}:\n```\n{result.output[:2000] if result.output else result.error}\n```\nTolka resultatet och ge en sammanfattning."}
                    ]

                    # Stream QWEN's interpretation
                    async for token, stats, agent_id in orchestrator.chat_stream(
                        messages=follow_up_messages,
                        request_id=request_id + "-followup",
                        profile="qwen"
                    ):
                        if token:
                            await manager.send_json(websocket, {
                                "sender": "agent",
                                "text": token,
                                "is_finished": False,
                                "agent_id": "qwen",
                            })
                        if stats:
                            final_stats = stats

                else:
                    # DANGEROUS tool - require confirmation
                    _pending_tool_confirmations[request_id] = {
                        "tool": tool_name,
                        "params": params,
                        "original_question": text,
                        "original_response": full_text,
                        "websocket": websocket,
                    }

                    await manager.send_json(websocket, {
                        "sender": "system",
                        "confirmation_required": {
                            "request_id": request_id,
                            "tool": tool_name,
                            "params": params,
                            "description": tool_def.description,
                            "message": f"⚠️ QWEN vill köra: {tool_name}({params}). Godkänn?"
                        },
                        "is_finished": False
                    })

                    await emit_system_log(
                        "tool_confirmation",
                        f"[VÄNTANDE] {tool_name} kräver bekräftelse",
                        "warn",
                        "qwen"
                    )

                    # Don't send final done message yet - wait for confirmation
                    return

        # Send completion message with full stats
        await manager.send_json(websocket, {
            "sender": "agent",
            "text": "",
            "is_finished": True,
            "model": final_stats.model if final_stats else agent.model,
            "provider": final_stats.provider if final_stats else agent.provider.value,
            "agent_id": final_stats.agent_id if final_stats else active_agent_id,
            "stats": {
                "tokens": final_stats.tokens_generated if final_stats else 0,
                "speed": round(final_stats.tokens_per_second, 1) if final_stats else 0,
                "duration_ms": final_stats.total_duration_ms if final_stats else 0,
                "provider": final_stats.provider if final_stats else agent.provider.value,
                "model": final_stats.model if final_stats else agent.model,
                "agent_id": final_stats.agent_id if final_stats else active_agent_id
            }
        })

        logger.info(f"[{request_id}] Antigravity complete via {active_agent_id}")

        # Emit completion log
        tokens = final_stats.tokens_generated if final_stats else 0
        speed = round(final_stats.tokens_per_second, 1) if final_stats else 0
        await emit_system_log(
            "generation_complete",
            f"[{agent.display_name}] Complete: {tokens} tokens @ {speed} tok/s",
            "success",
            active_agent_id
        )

    except Exception as e:
        logger.error(f"[{request_id}] Antigravity error: {e}")

        # Emit error log
        await emit_system_log(
            "error",
            f"[ERROR] {str(e)[:50]}",
            "error",
            agent.id.value if agent else None
        )
        await manager.send_json(websocket, {
            "sender": "agent",
            "text": f"Error: {str(e)}",
            "is_finished": True,
            "error": True
        })


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Main WebSocket endpoint for chat communication.

    Supports two protocols:
    1. Legacy: {"type": "chat", "messages": [...], "mode": "auto"}
    2. Antigravity: {"text": "message", "mode": "auto"}

    Server responds with streaming tokens and status updates.

    OPERATION VITAL SIGNS:
    - Starts GPU telemetry broadcast when first client connects
    - Broadcasts status_update packets every 2 seconds with GPU stats
    """
    await manager.connect(websocket)

    # Start GPU telemetry broadcast if not already running
    start_gpu_broadcast()

    # Start status pulse for Kiosk dashboard
    start_status_pulse()

    try:
        while True:
            # Receive message
            try:
                raw_data = await websocket.receive_text()
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON")
                continue

            # Detect protocol format
            if "text" in data and "type" not in data:
                # Antigravity protocol: {"text": "...", "mode": "..."}
                await handle_antigravity_message(websocket, data)
            else:
                # Legacy protocol with "type" field
                message_type = data.get("type", "chat")

                if message_type == "chat":
                    await handle_chat_message(websocket, data)
                elif message_type == "ping":
                    await handle_ping(websocket, data)
                elif message_type == "switch_profile":
                    await handle_switch_profile(websocket, data)
                else:
                    logger.warning(f"Unknown message type: {message_type}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# =============================================================================
# CASCADE WEBSOCKET ENDPOINT - Multi-Agent Pipeline
# =============================================================================

async def cascade_websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint för Multi-Agent Cascade (Planner → Coder → Reviewer).

    Protocol:
        Send: {"task": "Skriv en REST API...", "skip_review": false}
        Receive: {"phase": "planning|coding|reviewing|complete", "agent_id": "...", "token": "..."}
    """
    from ..services.cascade_orchestrator import cascade_orchestrator, CascadePhase

    await manager.connect(websocket)
    logger.info("Cascade WebSocket connected")

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)

            task = data.get("task", "")
            skip_review = data.get("skip_review", False)

            if not task:
                await manager.send_json(websocket, {
                    "phase": "error",
                    "error": "No task provided"
                })
                continue

            request_id = str(uuid.uuid4())
            logger.info(f"[{request_id}] Cascade started: {task[:100]}...")

            # Stream cascade phases
            async for result in cascade_orchestrator.execute_cascade(
                task=task,
                request_id=request_id,
                skip_review=skip_review
            ):
                packet = {
                    "phase": result.phase.value,
                    "agent_id": result.agent_id,
                    "token": result.content,
                }

                if result.stats:
                    packet["stats"] = {
                        "tokens": result.stats.tokens_generated,
                        "tokens_per_sec": result.stats.tokens_per_second,
                        "duration_ms": result.stats.total_duration_ms,
                    }

                await manager.send_json(websocket, packet)

            logger.info(f"[{request_id}] Cascade complete")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Cascade WebSocket error: {e}")
        manager.disconnect(websocket)
