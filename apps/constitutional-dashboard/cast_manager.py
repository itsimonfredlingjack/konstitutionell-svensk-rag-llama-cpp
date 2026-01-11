from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

try:
    from config import Config
except ImportError:  # pragma: no cover
    from dashboard.config import Config  # type: ignore


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else raw.strip()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[cast_manager {ts}] {msg}", flush=True)


def _resolve_catt_bin() -> str:
    """Return a working catt executable path or raise."""
    configured = _env_str("CATT_BIN", "catt")
    if os.path.sep in configured:
        if os.path.exists(configured):
            return configured
        raise RuntimeError(f"CATT_BIN points to missing file: {configured}")

    found = shutil.which(configured)
    if found:
        return found

    # Convenience fallback: if the repo has a local venv, use it.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_catt = os.path.join(repo_root, "venv", "bin", "catt")
    if os.path.exists(venv_catt):
        return venv_catt

    raise RuntimeError(
        "catt not found on PATH.\n"
        "Install it with:\n"
        "  pip install catt\n"
        "or point CATT_BIN to the catt executable."
    )


def _run(cmd: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )


def _catt_cast_site(catt_bin: str, device_name: str, url: str) -> None:
    """Cast site using catt, then use pychromecast to load URL in DashCast."""
    cmd = [catt_bin, "-d", device_name, "cast_site", url]
    _log(f"Running: {shlex.join(cmd)}")
    proc = _run(cmd, timeout_s=_env_float("CATT_CAST_TIMEOUT_SECONDS", 60.0))
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"catt cast_site failed (rc={proc.returncode}): {err}")

    # Wait a moment for DashCast to start
    time.sleep(2)

    # Use pychromecast to actually load the URL in DashCast
    try:
        import pychromecast
        from pychromecast.controllers.dashcast import DashCastController

        _log(f"Connecting to {device_name} via pychromecast...")
        chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[device_name])
        if not chromecasts:
            _log(f"Warning: Could not find device '{device_name}' via pychromecast")
            return

        cast = chromecasts[0]
        cast.wait()

        dashcast = DashCastController()
        cast.register_handler(dashcast)
        dashcast.load_url(url)
        _log(f"Loaded URL in DashCast: {url}")

        browser.stop_discovery()
    except ImportError:
        _log("Warning: pychromecast not available, using catt only")
    except Exception as e:
        _log(f"Warning: pychromecast failed: {e}, using catt only")


def _catt_info_json(catt_bin: str, device_name: str) -> dict[str, Any]:
    cmd = [catt_bin, "-d", device_name, "info", "--json-output"]
    proc = _run(cmd, timeout_s=_env_float("CATT_INFO_TIMEOUT_SECONDS", 15.0))
    raw = (proc.stdout or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_active_app(info: dict[str, Any], expected_app_id: str) -> bool:
    app_id = info.get("app_id")
    if app_id is None:
        return False
    return str(app_id) == expected_app_id


def _healthcheck_url(dashboard_url: str) -> str:
    """
    Compute a stable healthcheck URL for the dashboard server.

    Prefers DASHBOARD_HEALTHCHECK_URL if set; otherwise uses /api/stats (v2 endpoint)
    on the same scheme+host+port as dashboard_url.
    """
    override = os.getenv("DASHBOARD_HEALTHCHECK_URL")
    if override and override.strip():
        return override.strip()

    parts = urlsplit(dashboard_url)
    # Use v2 stats endpoint for healthcheck
    return urlunsplit((parts.scheme, parts.netloc, "/api/stats", "", ""))


def _wait_for_dashboard(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    while True:
        try:
            with urlopen(url, timeout=3.0) as resp:
                code = getattr(resp, "status", 200)
                if 200 <= int(code) < 500:
                    return
        except Exception:
            pass

        if time.time() >= deadline:
            raise RuntimeError(f"Dashboard not reachable: {url}")
        time.sleep(1.0)


def run_keepalive() -> None:
    """
    Cast the dashboard URL to a Nest Hub using catt, and keep it alive.

    This script intentionally shells out to catt (Cast All The Things) rather
    than using pychromecast directly.
    """
    cfg = Config.from_env()

    display_name = cfg.cast_display_name
    url = cfg.dashboard_public_url
    health_url = _healthcheck_url(url)

    keepalive_seconds = _env_float("CAST_KEEPALIVE_SECONDS", 30.0)
    recast_backoff = _env_float("CAST_RECAST_BACKOFF_SECONDS", 5.0)
    expected_app_id = _env_str("CAST_EXPECTED_APP_ID", "84912283")
    startup_wait_s = _env_float("DASHBOARD_STARTUP_WAIT_SECONDS", 20.0)

    _log(f"Target display: {display_name!r}")
    _log(f"Target URL: {url}")
    _log(f"Healthcheck URL: {health_url}")
    _log(f"Using keepalive_seconds={keepalive_seconds} recast_backoff={recast_backoff}")
    _log(f"Expected app_id={expected_app_id!r} (override via CAST_EXPECTED_APP_ID)")

    try:
        catt_bin = _resolve_catt_bin()
    except Exception as e:
        _log(f"Fatal: {type(e).__name__}: {e}")
        return

    _log(f"Using catt: {catt_bin}")

    while True:
        try:
            try:
                _wait_for_dashboard(health_url, timeout_s=startup_wait_s)
            except Exception as e:
                _log(
                    "Dashboard server not reachable yet. "
                    "Start Flask first, then this will cast automatically. "
                    f"({type(e).__name__}: {e})"
                )
                time.sleep(recast_backoff)
                continue

            _catt_cast_site(catt_bin, display_name, url)
            _log("Dashboard cast started (catt).")

            while True:
                time.sleep(keepalive_seconds)
                # If the server is down, re-casting won't help; wait until it returns.
                try:
                    _wait_for_dashboard(health_url, timeout_s=5.0)
                except Exception:
                    _log("Dashboard server unreachable; waiting…")
                    continue
                info = _catt_info_json(catt_bin, display_name)
                if not _is_active_app(info, expected_app_id):
                    current = str(info.get("app_id")) if info else "None"
                    _log(
                        "Cast inactive or switched apps "
                        f"(app_id={current!r} expected={expected_app_id!r}). Recasting…"
                    )
                    _catt_cast_site(catt_bin, display_name, url)

        except KeyboardInterrupt:
            _log("Interrupted. Exiting.")
            return
        except Exception as e:
            _log(f"Error: {type(e).__name__}: {e}")
            time.sleep(recast_backoff)


if __name__ == "__main__":
    run_keepalive()
