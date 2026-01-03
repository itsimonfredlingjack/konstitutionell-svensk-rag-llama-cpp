"""
Model Profiles - Metadata for UI
Optimized for RTX 4070 (12GB VRAM)

SYSTEM prompts finns i Modelfiles - inte här.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ProfileId(str, Enum):
    """Available profile identifiers"""
    PLANNER = "planner"       # PHI4-reasoning 14B
    GENERALIST = "generalist" # GPT-OSS 20B


@dataclass
class ModelProfile:
    """Configuration for an AI model profile (UI metadata only)"""
    id: ProfileId
    name: str
    display_name: str
    description: str
    model: str  # Ollama model name
    temperature: float
    max_tokens: int
    context_length: int
    estimated_vram_gb: float
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    icon: str = "robot"
    color: str = "#FF4FD8"
    strengths: list[str] = None

    def __post_init__(self):
        if self.strengths is None:
            self.strengths = []


# Profile definitions (UI metadata only - prompts in Modelfiles)
PROFILES: dict[ProfileId, ModelProfile] = {
    ProfileId.PLANNER: ModelProfile(
        id=ProfileId.PLANNER,
        name="Hermes3 8B",
        display_name="PLANNER",
        description="Planering och resonemang. Tool calling.",
        model="hermes3:8b",
        temperature=0.3,
        max_tokens=4096,
        context_length=8192,
        estimated_vram_gb=11.0,
        top_p=0.9,
        repeat_penalty=1.05,
        icon="map",
        color="#00f0ff",
        strengths=["Planering", "Resonemang", "Analys"],
    ),
    ProfileId.GENERALIST: ModelProfile(
        id=ProfileId.GENERALIST,
        name="Gemma3 12B",
        display_name="GENERALIST",
        description="Generalist-assistent. Balanserad kreativitet och precision.",
        model="gemma3:12b",
        temperature=0.7,
        max_tokens=4096,
        context_length=8192,
        estimated_vram_gb=9.0,
        top_p=0.9,
        repeat_penalty=1.05,
        icon="brain",
        color="#bd00ff",
        strengths=["Kodning", "Skrivande", "Analys"],
    ),
}


def get_profile(profile_id: str) -> ModelProfile:
    """Get profile by ID with fallback to GENERALIST."""
    try:
        return PROFILES[ProfileId(profile_id.lower())]
    except (ValueError, KeyError):
        return PROFILES[ProfileId.GENERALIST]


def get_all_profiles() -> list[ModelProfile]:
    """Get list of all available profiles."""
    return list(PROFILES.values())


def get_profile_by_model(model_name: str) -> Optional[ModelProfile]:
    """Find profile by Ollama model name."""
    for profile in PROFILES.values():
        if profile.model == model_name:
            return profile
    return None


def get_default_profile() -> ModelProfile:
    """Get the default profile."""
    return PROFILES[ProfileId.GENERALIST]


def calculate_total_vram() -> float:
    """Calculate total VRAM needed for all profiles loaded."""
    return sum(p.estimated_vram_gb for p in PROFILES.values())


# Profile status tracking
@dataclass
class ProfileStatus:
    """Runtime status for a profile"""
    profile_id: ProfileId
    is_loaded: bool = False
    is_loading: bool = False
    last_used: Optional[str] = None
    load_time_ms: Optional[int] = None


class ProfileManager:
    """Manages profile state for dual-model setup."""

    def __init__(self):
        self._status: dict[ProfileId, ProfileStatus] = {
            pid: ProfileStatus(profile_id=pid)
            for pid in ProfileId
        }
        self._active_profile: Optional[ProfileId] = None

    @property
    def active_profile(self) -> Optional[ModelProfile]:
        if self._active_profile:
            return PROFILES.get(self._active_profile)
        return None

    def _resolve_profile_id(self, profile_id) -> Optional[ProfileId]:
        """Resolve a profile ID to a ProfileId enum, or None if not found."""
        if isinstance(profile_id, ProfileId):
            return profile_id
        try:
            return ProfileId(str(profile_id).lower())
        except ValueError:
            return None

    def set_loaded(self, profile_id, loaded: bool = True) -> None:
        """Mark a profile as loaded in VRAM."""
        pid = self._resolve_profile_id(profile_id)
        if pid is None:
            return
        self._status[pid].is_loaded = loaded
        self._status[pid].is_loading = False

    def set_active(self, profile_id) -> None:
        """Mark a profile as currently active (being used)."""
        pid = self._resolve_profile_id(profile_id)
        if pid is None:
            return
        self._active_profile = pid
        self._status[pid].is_loaded = True
        self._status[pid].is_loading = False

    def set_loading(self, profile_id) -> None:
        """Mark a profile as currently loading."""
        pid = self._resolve_profile_id(profile_id)
        if pid is None:
            return
        self._status[pid].is_loading = True

    def get_status(self, profile_id: ProfileId) -> ProfileStatus:
        """Get status for a specific profile."""
        return self._status[profile_id]

    def get_all_status(self) -> dict[ProfileId, ProfileStatus]:
        """Get status for all profiles."""
        return self._status.copy()

    def get_loaded_profiles(self) -> list[ProfileId]:
        """Get list of currently loaded profiles."""
        return [pid for pid, status in self._status.items() if status.is_loaded]


# Global profile manager instance
profile_manager = ProfileManager()
