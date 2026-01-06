from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import Optional, Tuple


def _ensure_parent_on_syspath() -> None:
    """
    Add parent directory (where speak.py is expected to live) to sys.path.
    This matches the user requirement for dynamic/relative resolution.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)


_IMPORT_ERROR: Optional[str] = None
_GoogleHomeSpeaker = None


def _try_import_speaker() -> Tuple[Optional[object], Optional[str]]:
    global _IMPORT_ERROR, _GoogleHomeSpeaker

    if _GoogleHomeSpeaker is not None or _IMPORT_ERROR is not None:
        return _GoogleHomeSpeaker, _IMPORT_ERROR

    _ensure_parent_on_syspath()
    try:
        from speak import GoogleHomeSpeaker  # type: ignore

        _GoogleHomeSpeaker = GoogleHomeSpeaker
        _IMPORT_ERROR = None
        return _GoogleHomeSpeaker, None
    except Exception as e:
        _GoogleHomeSpeaker = None
        _IMPORT_ERROR = f"{type(e).__name__}: {e}"
        return None, _IMPORT_ERROR


def voice_available() -> bool:
    speaker_cls, _ = _try_import_speaker()
    return speaker_cls is not None


def voice_import_error() -> Optional[str]:
    _, err = _try_import_speaker()
    return err


@lru_cache(maxsize=4)
def _get_speaker(device_name: str):
    speaker_cls, err = _try_import_speaker()
    if speaker_cls is None:
        raise RuntimeError(f"speak.py unavailable: {err}")

    # Be tolerant of constructor signature differences.
    try:
        return speaker_cls(device_name=device_name)  # type: ignore[misc]
    except TypeError:
        return speaker_cls(device_name)  # type: ignore[misc]


def speak_text(text: str, device_name: str) -> None:
    speaker = _get_speaker(device_name)

    # Be tolerant of method naming differences.
    for method_name in ("say", "speak", "speak_text", "tts", "play"):
        method = getattr(speaker, method_name, None)
        if callable(method):
            method(text)
            return

    raise AttributeError("GoogleHomeSpeaker has no callable say/speak method")
