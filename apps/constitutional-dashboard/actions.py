from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


try:
    from storage import load_state, set_ollama_model, set_ollama_temperature
except ImportError:  # pragma: no cover
    from dashboard.storage import (  # type: ignore
        load_state,
        set_ollama_model,
        set_ollama_temperature,
    )


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    spoken_text: Optional[str] = None


def _run_cmd(argv: list[str], timeout_s: float = 8.0) -> tuple[int, str, str]:
    """Run command and return (rc, stdout, stderr)."""
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _ollama_tags_url(ollama_url: str) -> str:
    """Build a /api/tags URL from OLLAMA_URL variants."""
    raw = (ollama_url or "http://localhost:11434").strip()
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "http://" + raw

    parsed = urlsplit(raw)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else raw
    return base.rstrip("/") + "/api/tags"


def _get_installed_models(ollama_url: str) -> list[str]:
    tags_url = _ollama_tags_url(ollama_url)
    try:
        req = Request(tags_url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=3) as resp:
            data = resp.read().decode("utf-8")

        import json  # noqa: PLC0415

        payload = json.loads(data)
        models = payload.get("models") or []
        names = []
        for m in models:
            name = (m.get("name") if isinstance(m, dict) else None) or ""
            name = str(name).strip()
            if name:
                names.append(name)
        return names
    except Exception:
        # Fallback to CLI if API not reachable
        rc, out, _ = _run_cmd(["ollama", "list"], timeout_s=4.0)
        if rc != 0 or not out:
            return []
        names = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("name"):
                continue
            names.append(line.split()[0])
        return names


def _require_confirm(confirm: bool, label: str) -> Optional[ActionResult]:
    if confirm:
        return None
    return ActionResult(
        ok=False,
        message=f"Bekräftelse krävs för {label}. Tryck igen för att bekräfta.",
    )


def restart_ollama(*, ollama_url: str) -> ActionResult:
    """Restart Ollama service (best-effort)."""
    candidates = [
        ["systemctl", "restart", "ollama"],
        ["sudo", "-n", "systemctl", "restart", "ollama"],
        ["service", "ollama", "restart"],
        ["sudo", "-n", "service", "ollama", "restart"],
    ]

    last_err = ""
    for cmd in candidates:
        try:
            rc, out, err = _run_cmd(cmd, timeout_s=20.0)
        except Exception as e:  # pragma: no cover
            last_err = f"{type(e).__name__}: {e}"
            continue

        if rc == 0:
            # Verify server responds (non-blocking)
            tags_url = _ollama_tags_url(ollama_url)
            try:
                req = Request(tags_url, headers={"Accept": "application/json"})
                with urlopen(req, timeout=3):
                    pass
                return ActionResult(ok=True, message="Ollama omstartad och svarar.")
            except Exception:
                return ActionResult(
                    ok=True,
                    message="Ollama omstartad (väntar på att den ska starta upp).",
                )

        if err:
            last_err = err
        elif out:
            last_err = out

    hint = "Kör manuellt: sudo systemctl restart ollama"
    if last_err:
        return ActionResult(
            ok=False,
            message=f"Kunde inte starta om Ollama: {last_err}. {hint}",
        )
    return ActionResult(ok=False, message=f"Kunde inte starta om Ollama. {hint}")


def clear_ollama_cache() -> ActionResult:
    """Unload running models from Ollama (frees VRAM/runner cache)."""
    rc, out, err = _run_cmd(["ollama", "ps"], timeout_s=5.0)
    if rc != 0:
        return ActionResult(
            ok=False,
            message=f"Kunde inte läsa ollama ps: {err or 'fel'}",
        )

    models: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name"):
            continue
        models.append(line.split()[0])

    if not models:
        return ActionResult(
            ok=True,
            message="Ingen Ollama-cache att rensa (inga modeller laddade).",
        )

    stopped: list[str] = []
    failed: list[str] = []
    for name in models:
        rc2, _out2, err2 = _run_cmd(["ollama", "stop", name], timeout_s=20.0)
        if rc2 == 0:
            stopped.append(name)
        else:
            failed.append(f"{name} ({err2 or 'fel'})")

    if failed:
        return ActionResult(
            ok=False,
            message=(
                f"Rensade delvis. Stoppade: {', '.join(stopped)}. "
                f"Misslyckades: {', '.join(failed)}"
            ),
        )

    return ActionResult(
        ok=True,
        message=f"Rensade Ollama-cache. Stoppade: {', '.join(stopped)}",
    )


_KILL_PATTERNS: list[tuple[str, str]] = [
    (r"\bnext-server\b", "Next.js dev"),
    (r"\bnpm run (start|dev)\b", "npm dev"),
    (r"\bcursor-server\b", "Cursor server"),
    (r"\bextensionHost\b", "VSCode extensionHost"),
    (r"\blsp_server\.py\b", "Python LSP"),
]


def stop_heavy_processes(*, confirm: bool) -> ActionResult:
    """Stop known heavy dev/background processes (SIGTERM)."""
    need = _require_confirm(confirm, "Stoppa tunga processer")
    if need:
        return need

    rc, out, err = _run_cmd(
        ["ps", "-eo", "pid,pcpu,pmem,args", "--sort=-pcpu"],
        timeout_s=4.0,
    )
    if rc != 0 or not out:
        return ActionResult(ok=False, message=f"Kunde inte läsa processlista: {err or 'fel'}")

    me = os.getpid()
    candidates: list[tuple[int, str]] = []

    for line in out.splitlines()[1:80]:
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+(.*)$", line)
        if not m:
            continue
        pid = int(m.group(1))
        args = m.group(4)
        if pid == me:
            continue
        # Never kill Ollama itself.
        if "ollama" in args:
            continue

        for pat, _label in _KILL_PATTERNS:
            if re.search(pat, args):
                candidates.append((pid, args))
                break

    if not candidates:
        return ActionResult(ok=True, message="Inga matchande tunga processer hittades.")

    killed: list[str] = []
    failed: list[str] = []

    for pid, args in candidates:
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(f"{pid}: {args[:60]}")
        except Exception as e:  # pragma: no cover
            failed.append(f"{pid} ({type(e).__name__}: {e})")

    if failed:
        return ActionResult(
            ok=False,
            message=(
                f"Skickade SIGTERM till: {', '.join(killed)}. "
                f"Misslyckades: {', '.join(failed)}"
            ),
        )

    return ActionResult(ok=True, message=f"Skickade SIGTERM till: {', '.join(killed)}")


def switch_model(*, state_file: str, ollama_url: str) -> ActionResult:
    """Cycle OLLAMA_MODEL between installed models (persisted in state)."""
    installed = _get_installed_models(ollama_url)
    if not installed:
        return ActionResult(ok=False, message="Hittade inga Ollama-modeller (ollama list tomt).")

    preferred = [
        "gpt-oss:20b",
        "gptoss-agent:latest",
        "gptoss-agent",
        "ministral-3:14b",
    ]
    available = [m for m in preferred if m in installed]
    if not available:
        available = installed

    state = load_state(state_file)
    current = (state.ollama_model or os.getenv("OLLAMA_MODEL") or "").strip()
    if current not in available:
        current = available[0]

    idx = available.index(current)
    new_model = available[(idx + 1) % len(available)]

    os.environ["OLLAMA_MODEL"] = new_model
    set_ollama_model(state_file, new_model)

    return ActionResult(ok=True, message=f"Ollama-modell satt till: {new_model}")


def lower_temperature(*, state_file: str) -> ActionResult:
    """Decrease OLLAMA_TEMPERATURE by 0.1 down to 0.0 (persisted in state)."""
    state = load_state(state_file)
    t = float(state.ollama_temperature)
    new_t = max(0.0, round(t - 0.1, 2))

    os.environ["OLLAMA_TEMPERATURE"] = str(new_t)
    set_ollama_temperature(state_file, new_t)

    return ActionResult(ok=True, message=f"Temperatur satt till: {new_t}")


def reboot_server(*, confirm: bool) -> ActionResult:
    """Reboot host machine (requires confirm; best-effort)."""
    need = _require_confirm(confirm, "Reboot server")
    if need:
        return need

    candidates = [
        ["systemctl", "reboot"],
        ["sudo", "-n", "systemctl", "reboot"],
        ["sudo", "-n", "reboot"],
        ["reboot"],
    ]

    last_err = ""
    for cmd in candidates:
        try:
            rc, out, err = _run_cmd(cmd, timeout_s=5.0)
        except Exception as e:  # pragma: no cover
            last_err = f"{type(e).__name__}: {e}"
            continue
        if rc == 0:
            return ActionResult(ok=True, message="Omstart initierad.")
        if err:
            last_err = err
        elif out:
            last_err = out

    hint = "Kör manuellt: sudo reboot"
    if last_err:
        return ActionResult(ok=False, message=f"Kunde inte starta om servern: {last_err}. {hint}")
    return ActionResult(ok=False, message=f"Kunde inte starta om servern. {hint}")


def restart_system(*, confirm: bool) -> ActionResult:
    """Restart entire system stack (stop_system.sh && start_system.sh)."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(current_dir))
    stop_script = os.path.join(repo_root, "stop_system.sh")
    start_script = os.path.join(repo_root, "start_system.sh")

    if not os.path.exists(stop_script) or not os.path.exists(start_script):
        return ActionResult(
            ok=False,
            message=f"System scripts not found: {stop_script} / {start_script}",
        )

    try:
        # Run stop_system.sh (blocking, but with timeout)
        rc1, out1, err1 = _run_cmd(["bash", stop_script], timeout_s=30.0)
        if rc1 != 0:
            return ActionResult(
                ok=False,
                message=f"stop_system.sh failed (rc={rc1}): {err1 or out1}",
            )

        # Wait 2 seconds before restart (as specified)
        import time
        time.sleep(2.0)

        # Run start_system.sh (non-blocking, in background using Popen)
        # This prevents Flask from hanging while script runs
        subprocess.Popen(
            ["bash", start_script],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return ActionResult(ok=True, message="System restart initierad (körs i bakgrunden).")
    except Exception as e:
        return ActionResult(ok=False, message=f"System restart misslyckades: {type(e).__name__}: {e}")


def flush_memory(*, rag_status_url: Optional[str] = None) -> ActionResult:
    """Flush memory (clear conversation history) via RAG backend."""
    # Use RAG backend endpoint for context reset
    flush_url = "http://localhost:8900/api/constitutional/agent/context/reset"

    try:
        req = Request(flush_url, method="POST", headers={"Accept": "application/json"})
        with urlopen(req, timeout=5.0) as resp:
            if 200 <= resp.status < 300:
                return ActionResult(ok=True, message="Konversationshistorik rensad.")
            else:
                # Fallback to Ollama cache clear if endpoint returns error
                logger.debug(f"RAG flush endpoint returned status {resp.status}, falling back")
                return clear_ollama_cache()
    except Exception as e:
        # Fallback: try to clear Ollama cache as proxy
        logger.debug(f"RAG flush endpoint failed: {e}, falling back to Ollama cache clear")
        return clear_ollama_cache()


def wake_ping(*, ollama_url: str) -> ActionResult:
    """Wake/ping model (force into VRAM by making a small request to Llama server)."""
    # Send minimal POST request to Llama server completion endpoint
    wake_url = "http://localhost:8080/completion"
    import json

    try:
        payload = json.dumps({"prompt": "\n", "n_predict": 1}).encode("utf-8")
        req = Request(
            wake_url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urlopen(req, timeout=10.0) as resp:
            if 200 <= resp.status < 300:
                return ActionResult(ok=True, message="Modell pingad (försöker hålla i VRAM).")
            else:
                return ActionResult(ok=False, message=f"Llama server returnerade status {resp.status}")
    except Exception as e:
        return ActionResult(ok=False, message=f"Kunde inte pinga modell: {type(e).__name__}: {e}")


def dispatch_action(
    action: str,
    *,
    confirm: bool,
    silent_mode: bool,  # noqa: ARG001 - unused (legacy)
    speaker_name: str,  # noqa: ARG001 - unused (legacy)
    state_file: str,
    ollama_url: str,
    briefing_model: str,  # noqa: ARG001 - unused (legacy)
    system_reset_commands: list[list[str]],  # noqa: ARG001 - unused (legacy)
    rag_status_url: Optional[str] = None,  # For flush_memory
) -> ActionResult:
    """Dispatch an action by ID."""
    match action:
        case "restart_ollama":
            return restart_ollama(ollama_url=ollama_url)
        case "clear_cache":
            return clear_ollama_cache()
        case "stop_heavy_processes":
            return stop_heavy_processes(confirm=confirm)
        case "switch_model":
            return switch_model(state_file=state_file, ollama_url=ollama_url)
        case "lower_temperature":
            return lower_temperature(state_file=state_file)
        case "reboot_server":
            return reboot_server(confirm=confirm)
        case "restart_system":
            return restart_system(confirm=confirm)
        case "flush_memory":
            return flush_memory(rag_status_url=rag_status_url)
        case "wake_ping":
            return wake_ping(ollama_url=ollama_url)
        case _:
            return ActionResult(ok=False, message=f"Okänd åtgärd: {action}")
