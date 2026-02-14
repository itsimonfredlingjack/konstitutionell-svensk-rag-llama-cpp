"""
Tests for Adaptive Retrieval - Phase 4: Confidence-Based Escalation
===================================================================

Tests cover:
1. ConfidenceSignals computation
2. ConfidenceCalculator logic
3. EscalationPolicy configuration
4. AdaptiveResult structure
5. Escalation decision logic
6. Integration tests with impossible must_include
7. Regression tests

Reference: Self-RAG (Asai et al.) - Learning to Retrieve, Generate, and Critique
"""

import pytest
from app.services.confidence_signals import (
    DEFAULT_THRESHOLDS,
    AdaptiveResult,
    ConfidenceCalculator,
    ConfidenceSignals,
    EscalationPolicy,
)

# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def calculator():
    """Create a ConfidenceCalculator with default thresholds."""
    return ConfidenceCalculator()


@pytest.fixture
def high_confidence_results():
    """Mock results with high confidence signals."""
    return [
        {
            "id": "doc1",
            "text": "GDPR artikel 7 kräver samtycke för personuppgiftsbehandling. 2018:218 reglerar detta.",
            "score": 0.95,
            "metadata": {"doc_type": "sfs", "source": "riksdagen", "title": "Dataskyddslagen"},
        },
        {
            "id": "doc2",
            "text": "Samtycke enligt GDPR måste vara frivilligt och informerat.",
            "score": 0.88,
            "metadata": {"doc_type": "prop", "source": "regeringen", "title": "GDPR Proposition"},
        },
        {
            "id": "doc3",
            "text": "Personuppgiftsbehandling utan samtycke är förbjuden.",
            "score": 0.75,
            "metadata": {"doc_type": "sou", "source": "riksdagen", "title": "SOU 2017:39"},
        },
    ]


@pytest.fixture
def low_confidence_results():
    """Mock results with low confidence signals."""
    return [
        {
            "id": "doc1",
            "text": "Detta dokument handlar om något annat helt.",
            "score": 0.25,
            "metadata": {"doc_type": "mot", "source": "riksdagen", "title": "Motion A"},
        },
        {
            "id": "doc2",
            "text": "Ännu ett irrelevant dokument.",
            "score": 0.23,
            "metadata": {"doc_type": "mot", "source": "riksdagen", "title": "Motion B"},
        },
    ]


@pytest.fixture
def duplicate_results():
    """Mock results with near-duplicates."""
    return [
        {
            "id": "doc1",
            "text": "GDPR samtycke är viktigt.",
            "score": 0.8,
            "metadata": {
                "doc_type": "sfs",
                "source": "riksdagen",
                "title": "Samma titel här och där",
            },
        },
        {
            "id": "doc2",
            "text": "GDPR samtycke är viktigt.",
            "score": 0.75,
            "metadata": {
                "doc_type": "sfs",
                "source": "riksdagen",
                "title": "Samma titel här och där",
            },
        },
        {
            "id": "doc3",
            "text": "GDPR samtycke är viktigt.",
            "score": 0.7,
            "metadata": {
                "doc_type": "sfs",
                "source": "riksdagen",
                "title": "Samma titel här och där",
            },
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# CONFIDENCE SIGNALS TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestConfidenceSignals:
    """Tests for ConfidenceSignals dataclass."""

    def test_default_values(self):
        """ConfidenceSignals has correct default values."""
        signals = ConfidenceSignals()

        assert signals.top_score == 0.0
        assert signals.margin == 0.0
        assert signals.must_include_hit_rate == 0.0
        assert signals.overall_confidence == 0.0
        assert signals.confidence_tier == "unknown"

    def test_to_dict_serialization(self):
        """ConfidenceSignals serializes correctly."""
        signals = ConfidenceSignals(
            top_score=0.85,
            margin=0.15,
            must_include_hit_rate=1.0,
            must_include_total=3,
            must_include_found=3,
            overall_confidence=0.75,
            confidence_tier="high",
        )

        d = signals.to_dict()

        assert d["top_score"] == 0.85
        assert d["margin"] == 0.15
        assert d["must_include_hit_rate"] == 1.0
        assert d["must_include_found"] == "3/3"
        assert d["overall_confidence"] == 0.75
        assert d["confidence_tier"] == "high"


# ═══════════════════════════════════════════════════════════════════════════
# CONFIDENCE CALCULATOR TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestConfidenceCalculator:
    """Tests for ConfidenceCalculator logic."""

    def test_compute_empty_results(self, calculator):
        """Empty results → very_low confidence."""
        signals = calculator.compute(results=[], must_include=[])

        assert signals.confidence_tier == "very_low"
        assert signals.overall_confidence == 0.0

    def test_compute_high_confidence(self, calculator, high_confidence_results):
        """High-quality results → high confidence."""
        signals = calculator.compute(
            results=high_confidence_results,
            must_include=["GDPR", "samtycke"],
        )

        assert signals.top_score > 0.8
        assert signals.must_include_hit_rate == 1.0  # Both found
        assert signals.confidence_tier in ("high", "medium")

    def test_compute_low_confidence(self, calculator, low_confidence_results):
        """Low-quality results → low confidence."""
        signals = calculator.compute(
            results=low_confidence_results,
            must_include=["GDPR", "samtycke"],
        )

        assert signals.top_score < 0.5
        assert signals.must_include_hit_rate < 1.0
        assert signals.confidence_tier in ("low", "very_low")

    def test_compute_missing_must_include(self, calculator, high_confidence_results):
        """Missing must_include tokens → lower confidence."""
        signals = calculator.compute(
            results=high_confidence_results,
            must_include=["GDPR", "samtycke", "NONEXISTENT_TOKEN_12345"],
        )

        # 2/3 tokens found
        assert signals.must_include_hit_rate < 1.0
        assert signals.must_include_found == 2
        assert signals.must_include_total == 3

    def test_compute_sfs_must_include(self, calculator, high_confidence_results):
        """SFS numbers in must_include are found."""
        signals = calculator.compute(
            results=high_confidence_results,
            must_include=["2018:218"],
        )

        assert signals.must_include_hit_rate == 1.0
        assert signals.must_include_found == 1

    def test_compute_no_must_include(self, calculator, high_confidence_results):
        """No must_include → hit_rate defaults to 1.0."""
        signals = calculator.compute(
            results=high_confidence_results,
            must_include=[],
        )

        assert signals.must_include_hit_rate == 1.0
        assert signals.must_include_total == 0


class TestRerankerSignals:
    """Tests for reranker signal computation."""

    def test_top_score_calculation(self, calculator, high_confidence_results):
        """Top score extracted correctly."""
        signals = calculator.compute(high_confidence_results, [])

        assert signals.top_score == pytest.approx(0.95, abs=0.01)

    def test_margin_calculation(self, calculator, high_confidence_results):
        """Margin (top1 - top2) calculated correctly."""
        signals = calculator.compute(high_confidence_results, [])

        # 0.95 - 0.88 = 0.07
        # Normalized by score range (0.95 - 0.75 = 0.20)
        # 0.07 / 0.20 = 0.35
        assert signals.margin > 0

    def test_single_result_margin(self, calculator):
        """Single result → full margin."""
        results = [{"id": "a", "score": 0.8}]
        signals = calculator.compute(results, [])

        assert signals.margin == pytest.approx(0.8, abs=0.1)


class TestDiversitySignals:
    """Tests for diversity signal computation."""

    def test_near_duplicate_detection(self, calculator, duplicate_results):
        """Near-duplicates detected via title prefix."""
        signals = calculator.compute(duplicate_results, [])

        # 3 docs with same title prefix → 2 duplicates
        assert signals.near_duplicate_ratio > 0.5

    def test_unique_sources_count(self, calculator, high_confidence_results):
        """Unique sources counted correctly."""
        signals = calculator.compute(high_confidence_results, [])

        # 3 different doc_type:source combinations
        assert signals.unique_sources == 3


# ═══════════════════════════════════════════════════════════════════════════
# ESCALATION POLICY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestEscalationPolicy:
    """Tests for EscalationPolicy configuration."""

    def test_step_a_config(self):
        """Step A: baseline rag_fusion with 2 queries."""
        config = EscalationPolicy.get_step_config("A")

        assert config["strategy"] == "rag_fusion"
        assert config["num_queries"] == 2
        assert config["k_multiplier"] == 1.0

    def test_step_b_config(self):
        """Step B: increased k."""
        config = EscalationPolicy.get_step_config("B")

        assert config["k_multiplier"] == 2.0

    def test_step_c_config(self):
        """Step C: 3 queries."""
        config = EscalationPolicy.get_step_config("C")

        assert config["num_queries"] == 3

    def test_step_d_config(self):
        """Step D: fallback."""
        config = EscalationPolicy.get_step_config("D")

        assert config.get("fallback") is True

    def test_next_step_progression(self):
        """Steps progress A → B → C → D → None."""
        assert EscalationPolicy.next_step("A") == "B"
        assert EscalationPolicy.next_step("B") == "C"
        assert EscalationPolicy.next_step("C") == "D"
        assert EscalationPolicy.next_step("D") is None

    def test_all_steps(self):
        """All steps in correct order."""
        assert EscalationPolicy.all_steps() == ["A", "B", "C", "D"]


# ═══════════════════════════════════════════════════════════════════════════
# ESCALATION DECISION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestEscalationDecision:
    """Tests for should_escalate logic."""

    def test_escalate_on_low_top_score(self, calculator):
        """Low top_score triggers escalation."""
        signals = ConfidenceSignals(
            top_score=0.01,  # Below calibrated RRF threshold (0.05)
            margin=0.5,
            must_include_hit_rate=1.0,
            lexical_overlap=0.8,  # Avoid lexical overlap becoming primary reason
            overall_confidence=0.6,
        )

        should, reason = calculator.should_escalate(signals)

        assert should is True
        assert "top_score" in reason

    def test_escalate_on_low_margin(self, calculator):
        """Low margin triggers escalation."""
        signals = ConfidenceSignals(
            top_score=0.8,
            margin=0.001,  # Below calibrated RRF margin threshold (0.006)
            must_include_hit_rate=1.0,
            lexical_overlap=0.8,  # Avoid lexical overlap becoming primary reason
            overall_confidence=0.6,
        )

        should, reason = calculator.should_escalate(signals)

        assert should is True
        assert "margin" in reason

    def test_escalate_on_missing_must_include(self, calculator):
        """Missing must_include triggers escalation."""
        signals = ConfidenceSignals(
            top_score=0.8,
            margin=0.5,
            must_include_hit_rate=0.3,  # Below threshold
            must_include_total=3,
            must_include_found=1,
            overall_confidence=0.6,
        )

        should, reason = calculator.should_escalate(signals)

        assert should is True
        assert "must_include" in reason

    def test_escalate_on_high_duplicates(self, calculator):
        """High duplicate ratio triggers escalation."""
        signals = ConfidenceSignals(
            top_score=0.8,
            margin=0.5,
            must_include_hit_rate=1.0,
            near_duplicate_ratio=0.8,  # Above threshold
            overall_confidence=0.6,
        )

        should, reason = calculator.should_escalate(signals)

        assert should is True
        assert "duplicates" in reason

    def test_no_escalate_on_good_signals(self, calculator):
        """Good signals → no escalation."""
        signals = ConfidenceSignals(
            top_score=0.8,
            margin=0.3,
            must_include_hit_rate=1.0,
            near_duplicate_ratio=0.1,
            lexical_overlap=0.8,
            overall_confidence=0.7,
            confidence_tier="high",
        )

        should, reason = calculator.should_escalate(signals)

        assert should is False
        assert reason == "confidence OK"


# ═══════════════════════════════════════════════════════════════════════════
# CONFIDENCE TIER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestConfidenceTier:
    """Tests for confidence tier assignment."""

    def test_high_tier(self, calculator):
        """Score >= 0.7 → high."""
        assert calculator._tier_from_score(0.8) == "high"
        assert calculator._tier_from_score(0.7) == "high"

    def test_medium_tier(self, calculator):
        """Score 0.5-0.7 → medium."""
        assert calculator._tier_from_score(0.6) == "medium"
        assert calculator._tier_from_score(0.5) == "medium"

    def test_low_tier(self, calculator):
        """Score 0.3-0.5 → low."""
        assert calculator._tier_from_score(0.4) == "low"
        assert calculator._tier_from_score(0.3) == "low"

    def test_very_low_tier(self, calculator):
        """Score < 0.3 → very_low."""
        assert calculator._tier_from_score(0.2) == "very_low"
        assert calculator._tier_from_score(0.0) == "very_low"


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTIVE RESULT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestAdaptiveResult:
    """Tests for AdaptiveResult dataclass."""

    def test_to_dict_serialization(self):
        """AdaptiveResult serializes correctly."""
        signals = ConfidenceSignals(
            top_score=0.85,
            overall_confidence=0.75,
            confidence_tier="high",
        )

        result = AdaptiveResult(
            results=[{"id": "doc1"}],
            signals=signals,
            escalation_path=["A", "B"],
            final_step="B",
            final_strategy="rag_fusion",
            total_escalations=1,
            fallback_triggered=False,
        )

        d = result.to_dict()

        assert d["escalation_path"] == ["A", "B"]
        assert d["final_step"] == "B"
        assert d["total_escalations"] == 1
        assert d["fallback_triggered"] is False
        assert d["signals"]["overall_confidence"] == 0.75


# ═══════════════════════════════════════════════════════════════════════════
# WEIGHTED CONFIDENCE TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestWeightedConfidence:
    """Tests for overall confidence calculation."""

    def test_perfect_signals_high_confidence(self, calculator):
        """Perfect signals → high overall confidence."""
        results = [
            {
                "id": "a",
                "score": 1.0,
                "text": "GDPR samtycke",
                "metadata": {"doc_type": "sfs", "source": "a", "title": "A"},
            },
        ]

        signals = calculator.compute(results, ["GDPR", "samtycke"])

        assert signals.overall_confidence >= 0.6  # Should be reasonably high

    def test_weights_reflect_importance(self, calculator):
        """must_include has highest weight (0.30)."""
        # Same results, different must_include
        results = [
            {"id": "a", "score": 0.8, "text": "GDPR samtycke", "metadata": {}},
        ]

        signals_found = calculator.compute(results, ["GDPR"])
        signals_missing = calculator.compute(results, ["NONEXISTENT"])

        # Missing must_include should lower confidence significantly
        assert signals_missing.overall_confidence < signals_found.overall_confidence


# ═══════════════════════════════════════════════════════════════════════════
# THRESHOLD CONFIGURATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestThresholds:
    """Tests for threshold configuration."""

    def test_default_thresholds_exist(self):
        """Default thresholds are defined."""
        required_keys = [
            "top_score_low",
            "margin_low",
            "must_include_min",
            "fusion_gain_low",
            "overlap_high",
            "near_duplicate_max",
            "overall_confidence_low",
        ]

        for key in required_keys:
            assert key in DEFAULT_THRESHOLDS, f"Missing threshold: {key}"

    def test_custom_thresholds(self):
        """Custom thresholds can be provided."""
        custom = {"top_score_low": 0.5, "margin_low": 0.1}
        calculator = ConfidenceCalculator(thresholds=custom)

        assert calculator.thresholds["top_score_low"] == 0.5
        assert calculator.thresholds["margin_low"] == 0.1


# ═══════════════════════════════════════════════════════════════════════════
# FUSION METRICS INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestFusionMetricsIntegration:
    """Tests for fusion metrics in confidence calculation."""

    def test_fusion_metrics_included(self, calculator, high_confidence_results):
        """Fusion metrics are incorporated into signals."""
        fusion_metrics = {
            "fusion_gain": 0.5,
            "overlap_ratio": 0.7,
        }

        signals = calculator.compute(
            results=high_confidence_results,
            must_include=[],
            fusion_metrics=fusion_metrics,
        )

        assert signals.fusion_gain == 0.5
        assert signals.overlap_ratio == 0.7

    def test_no_fusion_metrics(self, calculator, high_confidence_results):
        """No fusion metrics → defaults to 0."""
        signals = calculator.compute(
            results=high_confidence_results,
            must_include=[],
            fusion_metrics=None,
        )

        assert signals.fusion_gain == 0.0
        assert signals.overlap_ratio == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case tests."""

    def test_results_without_score(self, calculator):
        """Results without 'score' field handled."""
        results = [
            {"id": "a", "text": "test", "metadata": {}},
            {"id": "b", "text": "test", "metadata": {}},
        ]

        signals = calculator.compute(results, [])

        # Should not raise, scores default to 0
        assert signals.top_score == 0.0

    def test_results_with_rrf_score(self, calculator):
        """RRF scores are used when available."""
        results = [
            {"id": "a", "rrf_score": 0.9, "text": "test", "metadata": {}},
            {"id": "b", "rrf_score": 0.8, "text": "test", "metadata": {}},
        ]

        signals = calculator.compute(results, [])

        assert signals.top_score == pytest.approx(0.9, abs=0.01)

    def test_results_with_distance(self, calculator):
        """ChromaDB _distance converted to similarity."""
        results = [
            {
                "id": "a",
                "_distance": 0.1,
                "text": "test",
                "metadata": {},
            },  # distance 0.1 → high similarity
            {"id": "b", "_distance": 0.5, "text": "test", "metadata": {}},
        ]

        signals = calculator.compute(results, [])

        # 1/(1+0.1) ≈ 0.909
        assert signals.top_score > 0.8

    def test_metadata_not_dict(self, calculator):
        """Non-dict metadata handled gracefully."""
        results = [
            {"id": "a", "score": 0.8, "text": "test", "metadata": "not a dict"},
        ]

        signals = calculator.compute(results, [])

        # Should not raise
        assert signals.unique_sources == 0


# ═══════════════════════════════════════════════════════════════════════════
# REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestRegression:
    """Regression tests to prevent breaking changes."""

    def test_confidence_signals_fields_stable(self):
        """ConfidenceSignals has expected fields."""
        signals = ConfidenceSignals()

        # These fields must exist
        assert hasattr(signals, "top_score")
        assert hasattr(signals, "margin")
        assert hasattr(signals, "must_include_hit_rate")
        assert hasattr(signals, "fusion_gain")
        assert hasattr(signals, "overlap_ratio")
        assert hasattr(signals, "near_duplicate_ratio")
        assert hasattr(signals, "overall_confidence")
        assert hasattr(signals, "confidence_tier")

    def test_escalation_steps_stable(self):
        """Escalation steps haven't changed."""
        steps = EscalationPolicy.all_steps()

        assert len(steps) == 4
        assert steps[0] == "A"
        assert steps[-1] == "D"

    def test_to_dict_keys_stable(self):
        """Serialization keys are stable."""
        signals = ConfidenceSignals()
        d = signals.to_dict()

        required_keys = [
            "top_score",
            "margin",
            "must_include_hit_rate",
            "fusion_gain",
            "overlap_ratio",
            "near_duplicate_ratio",
            "overall_confidence",
            "confidence_tier",
        ]

        for key in required_keys:
            assert key in d, f"Missing key in to_dict: {key}"
