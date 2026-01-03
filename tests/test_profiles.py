"""Tests for profile system"""

import pytest
from app.models.profiles import (
    ProfileId,
    ModelProfile,
    PROFILES,
    get_profile,
    get_all_profiles,
    get_default_profile,
)


def test_profile_ids_exist():
    """Test that all ProfileIds have corresponding profiles"""
    for pid in ProfileId:
        assert pid in PROFILES
        assert isinstance(PROFILES[pid], ModelProfile)


def test_get_profile_valid():
    """Test getting valid profiles"""
    qwen = get_profile("think")
    assert qwen.id == ProfileId.THINK
    assert qwen.model == "qwen3:14b"


def test_get_profile_invalid_fallback():
    """Test that invalid profile IDs fall back to CHILL"""
    profile = get_profile("invalid")
    assert profile.id == ProfileId.CHILL


def test_get_profile_case_insensitive():
    """Test case insensitivity"""
    assert get_profile("THINK").id == ProfileId.THINK
    assert get_profile("Think").id == ProfileId.THINK
    assert get_profile("think").id == ProfileId.THINK


def test_all_profiles():
    """Test getting all profiles"""
    profiles = get_all_profiles()
    assert len(profiles) == 2
    ids = [p.id for p in profiles]
    assert ProfileId.THINK in ids
    assert ProfileId.CHILL in ids


def test_default_profile():
    """Test default profile is CHILL"""
    default = get_default_profile()
    assert default.id == ProfileId.CHILL


def test_think_profile_config():
    """Test THINK profile configuration"""
    think = PROFILES[ProfileId.THINK]
    assert think.is_heavy is True
    assert think.estimated_vram_gb >= 9.0
    assert think.temperature < 0.5  # Deterministic
    assert think.max_tokens >= 4096


def test_chill_profile_config():
    """Test CHILL profile configuration"""
    chill = PROFILES[ProfileId.CHILL]
    assert chill.is_heavy is False
    assert chill.estimated_vram_gb <= 4.0
    assert chill.temperature > 0.3  # More creative
    assert chill.max_tokens >= 2048


def test_profile_has_system_prompt():
    """Test all profiles have system prompts"""
    for profile in PROFILES.values():
        assert profile.system_prompt
        assert len(profile.system_prompt) > 50
