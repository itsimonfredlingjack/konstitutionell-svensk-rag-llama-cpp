from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DashboardState:
    """Persisted dashboard settings."""

    silent_mode: bool = False
    ollama_model: str = "gptoss-agent"
    ollama_temperature: float = 0.2

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DashboardState:
        silent_mode = bool(data.get("silent_mode", False))
        ollama_model = str(data.get("ollama_model", "gptoss-agent") or "gptoss-agent")

        try:
            ollama_temperature = float(data.get("ollama_temperature", 0.2))
        except (TypeError, ValueError):
            ollama_temperature = 0.2

        if ollama_temperature < 0.0:
            ollama_temperature = 0.0
        if ollama_temperature > 2.0:
            ollama_temperature = 2.0

        return DashboardState(
            silent_mode=silent_mode,
            ollama_model=ollama_model,
            ollama_temperature=ollama_temperature,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "silent_mode": self.silent_mode,
            "ollama_model": self.ollama_model,
            "ollama_temperature": self.ollama_temperature,
        }


def load_state(path: str) -> DashboardState:
    try:
        with open(path, encoding="utf-8") as f:
            return DashboardState.from_dict(json.load(f))
    except FileNotFoundError:
        return DashboardState()
    except Exception:
        # If state is corrupted, fall back safely.
        return DashboardState()


def save_state(path: str, state: DashboardState) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def set_silent_mode(path: str, enabled: bool) -> DashboardState:
    state = load_state(path)
    new_state = DashboardState(
        silent_mode=enabled,
        ollama_model=state.ollama_model,
        ollama_temperature=state.ollama_temperature,
    )
    save_state(path, new_state)
    return new_state


def toggle_silent_mode(path: str) -> DashboardState:
    state = load_state(path)
    return set_silent_mode(path, not state.silent_mode)


def set_ollama_model(path: str, model: str) -> DashboardState:
    state = load_state(path)
    new_state = DashboardState(
        silent_mode=state.silent_mode,
        ollama_model=str(model or state.ollama_model),
        ollama_temperature=state.ollama_temperature,
    )
    save_state(path, new_state)
    return new_state


def set_ollama_temperature(path: str, temperature: float) -> DashboardState:
    state = load_state(path)
    try:
        t = float(temperature)
    except (TypeError, ValueError):
        t = state.ollama_temperature

    if t < 0.0:
        t = 0.0
    if t > 2.0:
        t = 2.0

    new_state = DashboardState(
        silent_mode=state.silent_mode,
        ollama_model=state.ollama_model,
        ollama_temperature=t,
    )
    save_state(path, new_state)
    return new_state
