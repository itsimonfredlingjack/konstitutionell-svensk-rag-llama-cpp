"""
Tests for Prompt Service — system prompt construction, context formatting, truncation detection.

Covers:
- build_llm_context (source formatting)
- build_system_prompt (EVIDENCE / ASSIST / CHAT modes)
- is_truncated_answer (truncation detection heuristics)
- format_constitutional_examples (RetICL formatting)
"""

import pytest
from unittest.mock import MagicMock

from app.services.prompt_service import (
    build_llm_context,
    build_system_prompt,
    format_constitutional_examples,
    is_truncated_answer,
)


# ── Helpers ───────────────────────────────────────────────────────


def _source(
    title="Test Doc",
    snippet="Test content.",
    score=0.85,
    doc_type="proposition",
):
    """Create a mock SearchResult."""
    s = MagicMock()
    s.title = title
    s.snippet = snippet
    s.score = score
    s.doc_type = doc_type
    return s


# ═══════════════════════════════════════════════════════════════════
# build_llm_context
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBuildLLMContext:
    def test_empty_sources(self):
        result = build_llm_context([])
        assert "Inga relevanta" in result

    def test_sources_formatted_with_kalla_prefix(self):
        sources = [_source(title="RF 2 kap.", snippet="Yttrandefrihet.", score=0.92)]
        result = build_llm_context(sources)
        assert "[Källa 1: RF 2 kap.]" in result
        assert "Yttrandefrihet." in result

    def test_sfs_gets_priority_marker(self):
        sources = [_source(title="SFS 2018:218", doc_type="sfs", score=0.9)]
        result = build_llm_context(sources)
        assert "PRIORITET (SFS)" in result

    def test_non_sfs_shows_doc_type(self):
        sources = [_source(title="Prop 2023/24:1", doc_type="proposition", score=0.8)]
        result = build_llm_context(sources)
        assert "PROPOSITION" in result

    def test_multiple_sources_numbered(self):
        sources = [
            _source(title="Doc A", score=0.9),
            _source(title="Doc B", score=0.8),
        ]
        result = build_llm_context(sources)
        assert "[Källa 1: Doc A]" in result
        assert "[Källa 2: Doc B]" in result

    def test_relevance_score_formatted(self):
        sources = [_source(score=0.8512)]
        result = build_llm_context(sources)
        assert "0.85" in result


# ═══════════════════════════════════════════════════════════════════
# build_system_prompt
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBuildSystemPrompt:
    def test_evidence_contains_identity_block(self):
        prompt = build_system_prompt("evidence", [], "context")
        assert "SYSTEMIDENTITET" in prompt

    def test_evidence_contains_grounding_evidence(self):
        prompt = build_system_prompt("evidence", [], "context")
        assert "CITERA ORDAGRANT" in prompt

    def test_evidence_contains_procedural_evidence(self):
        prompt = build_system_prompt("evidence", [], "context")
        assert "PROCEDURKONTROLL" in prompt

    def test_evidence_structured_output_json(self):
        prompt = build_system_prompt("evidence", [], "context", structured_output_enabled=True)
        assert "strikt JSON" in prompt
        assert '"svar"' in prompt

    def test_evidence_text_instruction_when_no_structured(self):
        prompt = build_system_prompt("evidence", [], "context", structured_output_enabled=False)
        assert "Spekulera aldrig" in prompt
        # Should NOT contain the JSON schema instruction block
        assert "strikt JSON" not in prompt

    def test_evidence_has_examples_placeholder(self):
        prompt = build_system_prompt("evidence", [], "context")
        assert "{{CONSTITUTIONAL_EXAMPLES}}" in prompt

    def test_evidence_includes_context_text(self):
        prompt = build_system_prompt("evidence", [], "my custom context goes here")
        assert "my custom context goes here" in prompt

    def test_assist_contains_grounding_assist(self):
        prompt = build_system_prompt("assist", [], "context")
        # ASSIST uses _GROUNDING_ASSIST which has "CITERA DIREKT"
        assert "CITERA DIREKT" in prompt

    def test_assist_contains_procedural_assist(self):
        prompt = build_system_prompt("assist", [], "context")
        assert "PROCEDURKONTROLL" in prompt or "PROCESS" in prompt

    def test_assist_has_examples_placeholder(self):
        prompt = build_system_prompt("assist", [], "context")
        assert "{{CONSTITUTIONAL_EXAMPLES}}" in prompt

    def test_chat_returns_chat_prompt(self):
        prompt = build_system_prompt("chat", [], "context")
        assert "Konstitutionell AI" in prompt
        assert "INGEN MARKDOWN" in prompt

    def test_chat_does_not_contain_json_instruction(self):
        prompt = build_system_prompt("chat", [], "context")
        assert "strikt JSON" not in prompt


# ═══════════════════════════════════════════════════════════════════
# is_truncated_answer
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestIsTruncatedAnswer:
    def test_empty_string(self):
        assert is_truncated_answer("") is True

    def test_complete_answer(self):
        assert is_truncated_answer("Complete answer.") is False

    def test_ends_with_colon(self):
        assert is_truncated_answer("Dessa steg:") is True

    def test_short_with_foljande(self):
        assert is_truncated_answer("Här är följande punkter") is True

    def test_short_with_dessa(self):
        assert is_truncated_answer("Titta på dessa regler") is True

    def test_long_answer_is_not_truncated(self):
        long_answer = "A" * 200 + " följande steg were completed."
        assert is_truncated_answer(long_answer) is False

    def test_valid_json_with_svar(self):
        import json

        payload = json.dumps({"svar": "Ett komplett svar.", "mode": "EVIDENCE"})
        assert is_truncated_answer(payload) is False

    def test_valid_json_truncated_svar(self):
        import json

        payload = json.dumps({"svar": "Dessa steg:", "mode": "EVIDENCE"})
        assert is_truncated_answer(payload) is True

    def test_none_like_empty(self):
        assert is_truncated_answer("") is True

    def test_ends_with_incomplete_list_pattern(self):
        assert is_truncated_answer("dessa steg:") is True
        assert is_truncated_answer("följande punkter:") is True


# ═══════════════════════════════════════════════════════════════════
# format_constitutional_examples
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFormatConstitutionalExamples:
    def test_empty_list_returns_empty_string(self):
        assert format_constitutional_examples([]) == ""

    def test_with_examples_contains_header(self):
        examples = [
            {
                "user": "Vad säger RF?",
                "assistant": {"svar": "RF reglerar...", "mode": "EVIDENCE"},
            }
        ]
        result = format_constitutional_examples(examples)
        assert "KONSTITUTIONELLA EXEMPEL" in result

    def test_with_examples_contains_content(self):
        examples = [
            {
                "user": "Test fråga",
                "assistant": {"svar": "Testsvar"},
            }
        ]
        result = format_constitutional_examples(examples)
        assert "Test fråga" in result
        assert "Testsvar" in result

    def test_multiple_examples_numbered(self):
        examples = [
            {"user": "Q1", "assistant": {"svar": "A1"}},
            {"user": "Q2", "assistant": {"svar": "A2"}},
        ]
        result = format_constitutional_examples(examples)
        assert "Exempel 1:" in result
        assert "Exempel 2:" in result
