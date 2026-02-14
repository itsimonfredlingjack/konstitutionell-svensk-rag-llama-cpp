"""
LLM Query Expansion Service
===========================

Generates alternate legal query formulations for improved retrieval recall.
"""

import json
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, List, Optional, Tuple

from ..utils.logging import get_logger
from .config_service import ConfigService, get_config_service
from .llm_service import LLMService, get_llm_service

logger = get_logger(__name__)

QUERY_EXPANSION_SYSTEM_PROMPT = (
    "Du är en svensk juridisk sökassistent. Generera exakt 3 alternativa "
    "formuleringar av användarens sökfråga för att förbättra sökning i juridiska "
    "dokument. Inkludera synonymer, relaterade juridiska termer, och "
    "SFS-relaterade formuleringar. Svara som en JSON-array med exakt 3 strängar."
)

QUERY_EXPANSION_GRAMMAR = r"""root ::= "[" ws item ("," ws item)* "]" ws
item ::= "\"" chars "\""
chars ::= char+
char ::= [^"\\] | "\\" ["\\/bfnrt]
ws ::= [ \t\n\r]*"""


@dataclass
class ExpansionResult:
    """Result of query expansion."""

    queries: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    grammar_requested: bool = False
    grammar_applied: bool = False
    parsing_method: str = "none"


class QueryExpansionService:
    """Service for LLM-based query expansion."""

    def __init__(self, config: ConfigService, llm_service: Optional[LLMService] = None):
        self.config = config
        self.llm_service = llm_service or get_llm_service(config)
        self.logger = logger

    async def expand(self, query: str, count: Optional[int] = None) -> ExpansionResult:
        """
        Generate alternate query formulations from a single LLM call.

        Returns fail-open empty list on any error.
        """
        start = time.perf_counter()

        normalized_query = self._normalize(query)
        if not normalized_query:
            return ExpansionResult(
                queries=[],
                latency_ms=0.0,
                success=False,
                error="empty query",
                grammar_requested=False,
                grammar_applied=False,
                parsing_method="none",
            )

        requested_count = count or getattr(self.config.settings, "query_expansion_count", 3)
        requested_count = max(1, int(requested_count))
        use_grammar = bool(getattr(self.config.settings, "query_expansion_use_grammar", True))

        messages = [
            {"role": "system", "content": QUERY_EXPANSION_SYSTEM_PROMPT},
            {"role": "user", "content": normalized_query},
        ]
        config_override = {
            "temperature": 0.0,
            "top_p": 1.0,
            "num_predict": 128,
        }
        if use_grammar:
            config_override["grammar"] = QUERY_EXPANSION_GRAMMAR

        try:
            grammar_applied = False
            try:
                response, _ = await self.llm_service.chat_complete(
                    messages=messages,
                    config_override=config_override,
                )
                grammar_applied = use_grammar
            except Exception as grammar_exc:
                if not use_grammar:
                    raise
                self.logger.debug(
                    "Query expansion request with grammar failed, retrying without grammar: %s",
                    grammar_exc,
                )
                no_grammar_override = dict(config_override)
                no_grammar_override.pop("grammar", None)
                response, _ = await self.llm_service.chat_complete(
                    messages=messages,
                    config_override=no_grammar_override,
                )
                grammar_applied = False

            self.logger.debug(
                "Query expansion raw output (grammar_requested=%s, grammar_applied=%s): %s",
                use_grammar,
                grammar_applied,
                self._truncate(response),
            )

            parsed, parse_method = self._parse_response(response)
            self.logger.debug("Query expansion parsing method: %s", parse_method)
            cleaned = self._clean_and_filter(parsed, normalized_query)
            final_queries = cleaned[:requested_count]
            self.logger.debug(
                "Query expansion produced %d expansions after dedupe/filter (requested=%d)",
                len(final_queries),
                requested_count,
            )

            return ExpansionResult(
                queries=final_queries,
                latency_ms=(time.perf_counter() - start) * 1000,
                success=True,
                grammar_requested=use_grammar,
                grammar_applied=grammar_applied,
                parsing_method=parse_method,
            )
        except Exception as exc:
            self.logger.warning(f"LLM query expansion failed (continuing without expansion): {exc}")
            return ExpansionResult(
                queries=[],
                latency_ms=(time.perf_counter() - start) * 1000,
                success=False,
                error=str(exc),
                grammar_requested=use_grammar,
                grammar_applied=False,
                parsing_method="none",
            )

    def _parse_response(self, response: str) -> Tuple[List[str], str]:
        """Parse query expansion output with fallbacks: json -> regex array -> line split."""
        text = (response or "").strip()

        # Step 1: parse whole response as JSON
        try:
            parsed = self._coerce_to_string_list(json.loads(text))
            if parsed:
                return parsed, "json"
        except Exception:
            pass

        # Step 2: regex extract first JSON array, then parse that
        match = re.search(r"\[.*?\]", text, flags=re.DOTALL)
        if match:
            try:
                parsed = self._coerce_to_string_list(json.loads(match.group(0)))
                if parsed:
                    return parsed, "regex"
            except Exception:
                pass

        # Step 3: split-based fallback (newlines/numbering/bullets)
        split_candidates = self._extract_by_split(text)
        if split_candidates:
            return split_candidates, "split"

        raise ValueError("no query expansions could be parsed from model response")

    def _coerce_to_string_list(self, value: Any) -> List[str]:
        """Coerce a parsed JSON payload into list[str] when possible."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

        if isinstance(value, dict):
            for key in ("queries", "expansions", "alternatives", "items"):
                nested = value.get(key)
                if isinstance(nested, list):
                    return [str(item).strip() for item in nested if str(item).strip()]

        return []

    def _extract_by_split(self, text: str) -> List[str]:
        """Aggressive fallback parser for non-JSON responses."""
        if not text:
            return []

        # First, prefer explicit quoted strings if present.
        quoted = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', text)
        quoted_items: List[str] = []
        for raw in quoted:
            try:
                quoted_items.append(json.loads(f'"{raw}"'))
            except Exception:
                quoted_items.append(raw)
        quoted_items = [item.strip() for item in quoted_items if item and item.strip()]
        if quoted_items:
            return quoted_items

        candidates: List[str] = []

        # Split by numbered list prefixes (e.g. "1. ...", "2) ...").
        numbered_segments = re.split(r"(?:^|\n)\s*\d+[\)\.\:\-]\s*", text)
        if len(numbered_segments) > 1:
            for segment in numbered_segments[1:]:
                first_line = segment.strip().splitlines()[0] if segment.strip() else ""
                cleaned = first_line.strip().strip(" \"'")
                if cleaned:
                    candidates.append(cleaned)
            if candidates:
                return candidates

        # Split by line and strip bullets / numbering.
        for line in text.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*•]|\d+[\)\.\:\-])\s*", "", line).strip().strip(" \"'")
            if cleaned:
                candidates.append(cleaned)
        if candidates:
            return candidates

        # Final attempt: delimiter split.
        for part in re.split(r"\s*[;\|]\s*", text):
            cleaned = part.strip().strip(" \"'")
            if cleaned:
                candidates.append(cleaned)

        return candidates

    def _clean_and_filter(self, queries: List[str], original_query: str) -> List[str]:
        """Normalize, dedupe, and remove variants identical to original."""
        out: List[str] = []
        seen = {original_query.casefold()}
        for raw in queries:
            cleaned = self._normalize(raw)
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
        return out

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _truncate(text: str, limit: int = 800) -> str:
        normalized = " ".join((text or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit] + "..."


@lru_cache()
def get_query_expansion_service(config: Optional[ConfigService] = None) -> QueryExpansionService:
    """Get singleton query expansion service."""
    if config is None:
        config = get_config_service()
    return QueryExpansionService(config=config, llm_service=get_llm_service(config))
