"""Profile system for AI models"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional


class ProfileId(Enum):
    """Profile identifiers"""
    THINK = "think"
    CHILL = "chill"


@dataclass
class ModelProfile:
    """Model configuration profile"""
    id: ProfileId
    model: str
    temperature: float
    max_tokens: int
    is_heavy: bool
    estimated_vram_gb: float
    system_prompt: str


# Profile definitions
PROFILES: Dict[ProfileId, ModelProfile] = {
    ProfileId.THINK: ModelProfile(
        id=ProfileId.THINK,
        model="qwen3:14b",
        temperature=0.3,
        max_tokens=4096,
        is_heavy=True,
        estimated_vram_gb=9.0,
        system_prompt="You are a thoughtful AI assistant. Think carefully about each response and provide detailed, accurate information."
    ),
    ProfileId.CHILL: ModelProfile(
        id=ProfileId.CHILL,
        model="qwen3:7b",
        temperature=0.7,
        max_tokens=2048,
        is_heavy=False,
        estimated_vram_gb=4.0,
        system_prompt="You are a friendly AI assistant. Provide helpful, conversational responses."
    ),
}


def get_profile(profile_id: str) -> ModelProfile:
    """Get profile by ID, with fallback to CHILL"""
    try:
        pid = ProfileId(profile_id.lower())
        return PROFILES[pid]
    except (ValueError, KeyError):
        return PROFILES[ProfileId.CHILL]


def get_all_profiles() -> list[ModelProfile]:
    """Get all profiles"""
    return list(PROFILES.values())


def get_default_profile() -> ModelProfile:
    """Get default profile (CHILL)"""
    return PROFILES[ProfileId.CHILL]