from __future__ import annotations

import os
import sys
import time
from typing import Any

try:
    from flask import Flask, jsonify, render_template, request
except ModuleNotFoundError as e:  # pragma: no cover
    if str(e) == "No module named 'flask'":
        print(
            "FEL: Flask saknas i denna Python-miljö.\n\n"
            "Kör dashboarden med repo-venv (Flask finns i `.venv`):\n"
            "  cd /home/ai-server/google-home-hack\n"
            "  .venv/bin/python dashboard/app.py\n\n"
            "Alternativt:\n"
            "  source .venv/bin/activate\n"
            "  python dashboard/app.py\n",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from e
    raise

try:
    from config import Config
    from storage import load_state
    from system_stats import get_system_status
except ImportError:  # pragma: no cover
    # Support running as module: python -m dashboard.app
    from dashboard.config import Config  # type: ignore
    from dashboard.storage import load_state  # type: ignore
    from dashboard.system_stats import get_system_status  # type: ignore

try:
    from actions import dispatch_action
except ImportError:  # pragma: no cover
    from dashboard.actions import dispatch_action  # type: ignore


CONFIG = Config.from_env()

app = Flask(__name__, template_folder="templates", static_folder="static")
_SERVER_START_TS = time.time()


def _file_mtime(path: str) -> float | None:
    try:
        return float(os.path.getmtime(path))
    except Exception:
        return None


def _require_auth() -> str | None:
    """Returns an error string if auth fails, otherwise None."""
    if not CONFIG.enable_auth:
        return None
    token = request.headers.get("X-API-Token") or request.args.get("token")
    if token and token == CONFIG.api_token:
        return None
    return "Unauthorized (missing or invalid DASHBOARD_API_TOKEN)."


@app.get("/")
def index():
    return render_template("index.html", rag_status_url=CONFIG.rag_status_url)


@app.get("/api/status")
def api_status():
    status = get_system_status()
    state = load_state(CONFIG.state_file)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(current_dir)
    brain_path = os.path.join(repo_root, "brain.py")
    speak_path = os.path.join(repo_root, "speak.py")
    actions_path = os.path.join(current_dir, "actions.py")

    return jsonify(
        {
            **status,
            "config": {
                "dashboard_public_url": CONFIG.dashboard_public_url,
                "cast_display_name": CONFIG.cast_display_name,
                "cast_speaker_name": CONFIG.cast_speaker_name,
            },
            "settings": {
                "ollama_model": state.ollama_model,
                "ollama_temperature": state.ollama_temperature,
            },
            "build": {
                "pid": os.getpid(),
                "started_at_ts": _SERVER_START_TS,
                "files": {
                    "dashboard/app.py": _file_mtime(__file__),
                    "dashboard/actions.py": _file_mtime(actions_path),
                    "brain.py": _file_mtime(brain_path),
                    "speak.py": _file_mtime(speak_path),
                },
            },
        }
    )


@app.get("/api/stats")
def api_stats():
    """V2 stats endpoint: returns vram_used, tps_current, context_usage, status, logs."""
    status = get_system_status()
    return jsonify(
        {
            "vram_used": status.get("vram_used"),
            "tps_current": status.get("tps_current"),
            "context_usage": status.get("context_usage"),
            "status": status.get("status", "offline"),
            "cpu": status.get("cpu", {}).get("percent"),
            "ts": status.get("ts"),
            "logs": status.get("logs", []),
        }
    )


@app.get("/api/actions")
def api_actions():
    return jsonify(
        {
            "actions": [
                {
                    "id": "restart_ollama",
                    "title": "STARTA OM OLLAMA",
                    "description": "Försök starta om Ollama-tjänsten.",
                    "dangerous": False,
                },
                {
                    "id": "clear_cache",
                    "title": "RENSA CACHE",
                    "description": "Stoppar laddade Ollama-modeller (frigör VRAM).",
                    "dangerous": False,
                },
                {
                    "id": "stop_heavy_processes",
                    "title": "STOPPA TUNGA PROCESSER",
                    "description": "Skicka SIGTERM till kända tunga dev-processer.",
                    "dangerous": True,
                },
                {
                    "id": "switch_model",
                    "title": "BYT MODELL",
                    "description": "Växlar OLLAMA_MODEL (sparas i dashboard-state).",
                    "dangerous": False,
                },
                {
                    "id": "lower_temperature",
                    "title": "SÄNK TEMPERATUR",
                    "description": "Sänker OLLAMA_TEMPERATURE med 0.1 (min 0.0).",
                    "dangerous": False,
                },
                {
                    "id": "reboot_server",
                    "title": "REBOOT SERVER",
                    "description": "Starta om hela servern (kräver bekräftelse).",
                    "dangerous": True,
                },
            ]
        }
    )


@app.post("/api/trigger")
def api_trigger():
    auth_err = _require_auth()
    if auth_err:
        return jsonify({"ok": False, "message": auth_err}), 401

    payload: dict[str, Any] = request.get_json(force=True, silent=True) or {}
    action = str(payload.get("action", "")).strip()
    confirm = bool(payload.get("confirm", False))

    if not action:
        return jsonify({"ok": False, "message": "Missing action."}), 400

    state = load_state(CONFIG.state_file)
    result = dispatch_action(
        action,
        confirm=confirm,
        silent_mode=state.silent_mode,
        speaker_name=CONFIG.cast_speaker_name,
        state_file=CONFIG.state_file,
        ollama_url=CONFIG.ollama_url,
        briefing_model=CONFIG.briefing_model,
        system_reset_commands=CONFIG.system_reset_commands,
        rag_status_url=CONFIG.rag_status_url,
    )

    code = 200 if result.ok else 400
    return (
        jsonify({"ok": result.ok, "message": result.message, "spoken_text": result.spoken_text}),
        code,
    )


@app.post("/api/action/restart")
def api_action_restart():
    """Restart entire system stack."""
    auth_err = _require_auth()
    if auth_err:
        return jsonify({"ok": False, "message": auth_err}), 401

    state = load_state(CONFIG.state_file)
    result = dispatch_action(
        "restart_system",
        confirm=True,
        silent_mode=state.silent_mode,
        speaker_name=CONFIG.cast_speaker_name,
        state_file=CONFIG.state_file,
        ollama_url=CONFIG.ollama_url,
        briefing_model=CONFIG.briefing_model,
        system_reset_commands=CONFIG.system_reset_commands,
        rag_status_url=CONFIG.rag_status_url,
    )

    code = 200 if result.ok else 400
    return jsonify({"ok": result.ok, "message": result.message}), code


@app.post("/api/action/flush")
def api_action_flush():
    """Flush memory (clear conversation history)."""
    auth_err = _require_auth()
    if auth_err:
        return jsonify({"ok": False, "message": auth_err}), 401

    state = load_state(CONFIG.state_file)
    result = dispatch_action(
        "flush_memory",
        confirm=False,
        silent_mode=state.silent_mode,
        speaker_name=CONFIG.cast_speaker_name,
        state_file=CONFIG.state_file,
        ollama_url=CONFIG.ollama_url,
        briefing_model=CONFIG.briefing_model,
        system_reset_commands=CONFIG.system_reset_commands,
        rag_status_url=CONFIG.rag_status_url,
    )

    code = 200 if result.ok else 400
    return jsonify({"ok": result.ok, "message": result.message}), code


@app.post("/api/action/ping")
def api_action_ping():
    """Wake/ping model (force into VRAM)."""
    auth_err = _require_auth()
    if auth_err:
        return jsonify({"ok": False, "message": auth_err}), 401

    state = load_state(CONFIG.state_file)
    result = dispatch_action(
        "wake_ping",
        confirm=False,
        silent_mode=state.silent_mode,
        speaker_name=CONFIG.cast_speaker_name,
        state_file=CONFIG.state_file,
        ollama_url=CONFIG.ollama_url,
        briefing_model=CONFIG.briefing_model,
        system_reset_commands=CONFIG.system_reset_commands,
        rag_status_url=CONFIG.rag_status_url,
    )

    code = 200 if result.ok else 400
    return jsonify({"ok": result.ok, "message": result.message}), code


if __name__ == "__main__":
    # Critical: bind to 0.0.0.0 for LAN access (Nest Hub)
    app.run(host=CONFIG.dashboard_host, port=CONFIG.dashboard_port)
