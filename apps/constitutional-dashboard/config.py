from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else raw.strip()


def _parse_json_env(name: str) -> Optional[Any]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_reset_commands() -> list[list[str]]:
    """
    Parse SYSTEM_RESET_COMMANDS.

    Supported formats:
    - JSON: [["systemctl","--user","restart","serviceA"], ["..."]]
    - Comma-separated shell-ish strings: "cmd1 arg, cmd2 arg"
      (will be split on whitespace; use JSON for safer quoting)
    """
    parsed = _parse_json_env("SYSTEM_RESET_COMMANDS")
    if isinstance(parsed, list):
        commands: list[list[str]] = []
        for item in parsed:
            if isinstance(item, list) and all(isinstance(x, str) for x in item):
                commands.append([x for x in item if x.strip() != ""])
            elif isinstance(item, str) and item.strip():
                commands.append(item.strip().split())
        return [c for c in commands if c]

    raw = os.getenv("SYSTEM_RESET_COMMANDS")
    if raw is None or raw.strip() == "":
        return []
    commands = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        commands.append(part.split())
    return [c for c in commands if c]


@dataclass(frozen=True)
class Config:
    dashboard_host: str
    dashboard_port: int
    dashboard_public_url: str

    api_token: Optional[str]
    enable_auth: bool

    cast_display_name: str
    cast_speaker_name: str

    rag_status_url: Optional[str]

    ollama_url: str
    briefing_model: str

    state_file: str
    system_reset_commands: list[list[str]]

    @staticmethod
    def from_env() -> "Config":
        host = _env_str("DASHBOARD_HOST", "0.0.0.0")
        port_raw = _env_str("DASHBOARD_PORT", "5000")
        try:
            port = int(port_raw)
        except ValueError:
            port = 5000

        public_url = _env_str("DASHBOARD_PUBLIC_URL", "http://192.168.86.32:5000")

        api_token = os.getenv("DASHBOARD_API_TOKEN")
        enable_auth = api_token is not None and api_token.strip() != ""

        cast_display_name = _env_str("CAST_DISPLAY_NAME", "Sovis")
        cast_speaker_name = _env_str("CAST_SPEAKER_NAME", "Kontor")

        rag_status_url = os.getenv("RAG_STATUS_URL")
        if rag_status_url is not None:
            rag_status_url = rag_status_url.strip() or None

        ollama_url = _env_str("OLLAMA_URL", "http://localhost:11434")
        briefing_model = _env_str("BRIEFING_MODEL", "ministral-3:14b")

        state_file = _env_str(
            "DASHBOARD_STATE_FILE",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"),
        )

        system_reset_commands = _parse_reset_commands()

        return Config(
            dashboard_host=host,
            dashboard_port=port,
            dashboard_public_url=public_url,
            api_token=api_token.strip() if api_token else None,
            enable_auth=enable_auth,
            cast_display_name=cast_display_name,
            cast_speaker_name=cast_speaker_name,
            rag_status_url=rag_status_url,
            ollama_url=ollama_url,
            briefing_model=briefing_model,
            state_file=state_file,
            system_reset_commands=system_reset_commands,
        )
