"""
Generation Service — LLM response generation, structured output parsing, and critic/revise.

Extracted from orchestrator_service.py (Sprint 2, Task #19).
Handles structured output parsing with 3-attempt retry, truncation detection/retry,
and the critic→revise loop.
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logging import get_logger
from .config_service import ConfigService
from .query_processor_service import ResponseMode

logger = get_logger(__name__)


@dataclass
class GenerationResult:
    """Result from the LLM generation + post-processing pipeline."""

    answer: str
    structured_data: Optional[Dict[str, Any]] = None
    parse_errors: bool = False
    structured_output_ms: float = 0.0
    critic_revision_count: int = 0
    critic_ms: float = 0.0
    critic_ok: bool = False
    sources_cleared: bool = False  # True if critic forced source clearing


async def process_structured_output(
    *,
    config: ConfigService,
    structured_output_service: Any,
    llm_service: Any,
    critic_service: Optional[Any],
    full_answer: str,
    mode: ResponseMode,
    question: str,
    system_prompt: str,
    llm_config: dict,
    sources: list,
    reasoning_steps: List[str],
    create_fallback_fn,
) -> GenerationResult:
    """
    Parse, validate, and retry structured output from LLM response.

    Handles:
    1. 3-attempt structured output parsing with retry
    2. Anti-truncation retry loop
    3. Critic→Revise loop (if enabled)

    Returns GenerationResult with final answer and metadata.
    """
    structured_output_start = time.perf_counter()
    structured_output_data = None
    parse_errors = False

    if config.structured_output_effective_enabled and mode != ResponseMode.CHAT:
        structured_output_data, parse_errors, full_answer = await _parse_with_retry(
            structured_output_service=structured_output_service,
            llm_service=llm_service,
            full_answer=full_answer,
            mode=mode,
            question=question,
            system_prompt=system_prompt,
            llm_config=llm_config,
            reasoning_steps=reasoning_steps,
            create_fallback_fn=create_fallback_fn,
        )

    structured_output_ms = (time.perf_counter() - structured_output_start) * 1000

    # Update answer from structured output
    if structured_output_data and "svar" in structured_output_data:
        full_answer = structured_output_data["svar"]

    # Anti-truncation retry
    full_answer = await _anti_truncation_retry(
        llm_service=llm_service,
        full_answer=full_answer,
        question=question,
        messages=[{"role": "system", "content": system_prompt}],
        llm_config=llm_config,
        structured_output_data=structured_output_data,
        reasoning_steps=reasoning_steps,
    )

    # Critic→Revise loop
    critic_revision_count = 0
    critic_ms = 0.0
    critic_ok = False
    sources_cleared = False

    if (
        config.critic_revise_effective_enabled
        and critic_service
        and structured_output_data
        and mode != ResponseMode.CHAT
    ):
        result = await _critic_revise_loop(
            config=config,
            critic=critic_service,
            structured_output_data=structured_output_data,
            full_answer=full_answer,
            mode=mode,
            sources=sources,
            reasoning_steps=reasoning_steps,
        )
        full_answer = result["answer"]
        structured_output_data = result["structured_data"]
        critic_revision_count = result["revision_count"]
        critic_ms = result["critic_ms"]
        critic_ok = result["critic_ok"]
        sources_cleared = result["sources_cleared"]

    # Log metrics
    if config.structured_output_effective_enabled and mode != ResponseMode.CHAT:
        logger.info(
            f"Structured output: mode={mode.value}, "
            f"parse_errors={parse_errors}, "
            f"latency_ms={structured_output_ms:.1f}, "
            f"saknas_underlag={structured_output_data.get('saknas_underlag', False) if structured_output_data else None}, "
            f"kallor_count={len(structured_output_data.get('kallor', [])) if structured_output_data else 0}"
        )

    return GenerationResult(
        answer=full_answer,
        structured_data=structured_output_data,
        parse_errors=parse_errors,
        structured_output_ms=structured_output_ms,
        critic_revision_count=critic_revision_count,
        critic_ms=critic_ms,
        critic_ok=critic_ok,
        sources_cleared=sources_cleared,
    )


async def _parse_with_retry(
    *,
    structured_output_service,
    llm_service,
    full_answer: str,
    mode: ResponseMode,
    question: str,
    system_prompt: str,
    llm_config: dict,
    reasoning_steps: List[str],
    create_fallback_fn,
) -> Tuple[Optional[Dict], bool, str]:
    """3-attempt structured output parsing. Returns (data, parse_errors, answer)."""

    def try_parse(text: str, attempt: int):
        try:
            json_output = structured_output_service.parse_llm_json(text)
            is_valid, errors, schema = structured_output_service.validate_output(
                json_output, mode.value
            )
            if is_valid and schema:
                return True, schema, None
            return False, None, f"Validation failed attempt {attempt}: {', '.join(errors)}"
        except json.JSONDecodeError as e:
            return False, None, f"JSON parsing failed attempt {attempt}: {str(e)[:100]}"

    # Attempt 1
    ok, schema, err = try_parse(full_answer, 1)
    if ok and schema:
        data = structured_output_service.strip_internal_note(schema)
        reasoning_steps.append("Structured output validation: PASSED (attempt 1)")
        return data, False, full_answer

    # Attempt 1 failed
    parse_errors = True
    reasoning_steps.append(f"Structured output validation: FAILED attempt 1 ({err})")
    logger.warning(f"Structured output attempt 1 failed: {err}")

    # Attempt 2: Retry with error-aware instruction
    try:
        retry_instruction = (
            f"Du returnerade ogiltig JSON med följande fel: {err}. "
            "Korrigera felet och returnera endast giltig JSON enligt schema. "
            "OBS: I EVIDENCE-läge MÅSTE 'fakta_utan_kalla' vara en TOM lista []."
        )
        retry_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Fråga: {question}"},
            {"role": "assistant", "content": f"Försökte att returnera JSON men fick fel: {err}"},
            {"role": "user", "content": retry_instruction},
        ]

        retry_answer = ""
        async for token, _ in llm_service.chat_stream(
            messages=retry_messages, config_override=llm_config
        ):
            retry_answer += token

        ok2, schema2, err2 = try_parse(retry_answer, 2)
        if ok2 and schema2:
            data = structured_output_service.strip_internal_note(schema2)
            reasoning_steps.append("Structured output validation: PASSED (attempt 2 - retry)")
            return data, True, full_answer

        reasoning_steps.append(f"Structured output validation: FAILED attempt 2 ({err2})")

        # Attempt 3: JSON-only reformat
        try:
            reformat_messages = [
                {
                    "role": "system",
                    "content": "Du är en JSON-formaterare. Returnera ENDAST giltig JSON, ingen annan text.",
                },
                {
                    "role": "user",
                    "content": f"Konvertera detta till giltig JSON med fälten 'svar' och 'kallor':\n\n{retry_answer[:2000]}",
                },
            ]
            reformat_answer = ""
            async for token, _ in llm_service.chat_stream(
                messages=reformat_messages,
                config_override={"temperature": 0.0, "num_predict": 1024},
            ):
                reformat_answer += token

            ok3, schema3, err3 = try_parse(reformat_answer, 3)
            if ok3 and schema3:
                data = structured_output_service.strip_internal_note(schema3)
                reasoning_steps.append(
                    "Structured output validation: PASSED (attempt 3 - JSON reformat)"
                )
                return data, True, full_answer

            reasoning_steps.append(f"Structured output validation: FAILED attempt 3 ({err3})")
            logger.error(f"JSON REFORMAT FAILED - raw output: {retry_answer[:500]!r}")
            answer, data = create_fallback_fn(mode, reasoning_steps)
            return data, True, answer

        except Exception as e:
            reasoning_steps.append(f"JSON reformat attempt 3 failed: {str(e)[:100]}")
            logger.error(f"JSON REFORMAT ERROR: {e}")
            answer, data = create_fallback_fn(mode, reasoning_steps)
            return data, True, answer

    except Exception as e:
        reasoning_steps.append(f"Attempt 2 failed unexpectedly: {str(e)[:100]}")
        logger.warning(f"Attempt 2 failed unexpectedly: {e}")
        logger.error(f"STRUCTURED OUTPUT FAILED - raw: {full_answer[:500]!r}")
        answer, data = create_fallback_fn(mode, reasoning_steps)
        return data, True, answer


async def _anti_truncation_retry(
    *,
    llm_service,
    full_answer: str,
    question: str,
    messages: list,
    llm_config: dict,
    structured_output_data: Optional[Dict],
    reasoning_steps: List[str],
    max_retries: int = 3,
) -> str:
    """Retry LLM generation if answer appears truncated."""
    if not full_answer:
        return full_answer

    best_answer = full_answer
    retry_count = 0

    while (
        full_answer
        and (len(full_answer.strip()) < 150 or full_answer.strip().endswith(":"))
        and retry_count < max_retries
    ):
        retry_count += 1
        logger.warning(
            f"TRUNCATION DETECTED (attempt {retry_count}/{max_retries}): len={len(full_answer)}"
        )
        try:
            retry_messages = []
            if messages and messages[0].get("role") == "system":
                retry_messages.append(messages[0])

            prompts = [
                f"{question}\n\nVIKTIGT: Ge ett KOMPLETT svar med ALLA detaljer. Lista MINST 5 steg med förklaringar.",
                f"Besvara följande fråga utförligt och konkret med minst 5 punkter:\n\n{question}",
                f"Förklara steg-för-steg med konkreta exempel:\n\n{question}\n\nInkludera alla relevanta lagar och paragrafer.",
            ]
            retry_messages.append({"role": "user", "content": prompts[min(retry_count - 1, 2)]})

            retry_config = dict(llm_config)
            retry_config["num_predict"] = 2000
            retry_config["temperature"] = 0.4 + (retry_count * 0.15)

            retry_answer = ""
            async for token, _ in llm_service.chat_stream(
                messages=retry_messages, config_override=retry_config
            ):
                if token:
                    retry_answer += token

            retry_svar = retry_answer
            try:
                parsed = json.loads(retry_answer)
                retry_svar = parsed.get("svar", retry_answer)
                if (
                    "svar" in parsed
                    and len(retry_svar) > len(full_answer)
                    and structured_output_data is not None
                ):
                    structured_output_data.update(parsed)
            except Exception:
                pass

            ends_colon = retry_svar.strip().endswith(":")
            if not ends_colon and len(retry_svar) > len(best_answer):
                best_answer = retry_svar

            if len(retry_svar) > len(full_answer) and not ends_colon:
                full_answer = retry_svar
                reasoning_steps.append(
                    f"Truncation fixed on attempt {retry_count} ({len(full_answer)} chars)"
                )
                break

        except Exception as e:
            logger.error(f"TRUNCATION RETRY {retry_count} ERROR: {e}")

    # Use best answer if current is still truncated
    if (len(full_answer.strip()) < 150 or full_answer.strip().endswith(":")) and len(
        best_answer
    ) > len(full_answer):
        full_answer = best_answer
        reasoning_steps.append(f"Used best retry answer ({len(full_answer)} chars)")

    return full_answer


async def _critic_revise_loop(
    *,
    config: ConfigService,
    critic,
    structured_output_data: Dict,
    full_answer: str,
    mode: ResponseMode,
    sources: list,
    reasoning_steps: List[str],
) -> Dict:
    """Run the critic→revise loop. Returns dict with results."""
    critic_start = time.perf_counter()
    current_json = json.dumps(structured_output_data, ensure_ascii=False)
    sources_context = [
        {"id": s.id, "title": s.title, "snippet": s.snippet, "score": s.score} for s in sources
    ]

    max_revisions = min(2, getattr(config.settings, "critic_max_revisions", 2))
    revision_count = 0
    feedback = None
    sources_cleared = False

    while revision_count < max_revisions:
        feedback = await critic.critique(
            candidate_json=current_json, mode=mode.value, sources_context=sources_context
        )

        if feedback.ok:
            break

        if revision_count < max_revisions - 1:
            revised_json = await critic.revise(
                candidate_json=current_json, critic_feedback=feedback
            )
            try:
                revised_data = json.loads(revised_json)
                current_json = revised_json
                structured_output_data = revised_data
                if "svar" in revised_data:
                    full_answer = revised_data["svar"]
                revision_count += 1
            except json.JSONDecodeError:
                break
        else:
            revision_count += 1
            break

    critic_ms = (time.perf_counter() - critic_start) * 1000
    critic_ok = feedback.ok if feedback else False

    logger.info(
        f"Critic: mode={mode.value}, revisions={revision_count}, "
        f"ok={critic_ok}, latency_ms={critic_ms:.1f}"
    )

    # Enforce fallback when critic still fails
    if feedback and not feedback.ok and revision_count >= max_revisions:
        if mode == ResponseMode.EVIDENCE:
            refusal_text = getattr(
                config.settings,
                "evidence_refusal_template",
                "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats...",
            )
            structured_output_data = {
                "mode": "EVIDENCE",
                "saknas_underlag": True,
                "svar": refusal_text,
                "kallor": [],
                "fakta_utan_kalla": [],
            }
            full_answer = refusal_text
            sources_cleared = True
        else:
            safe_fallback = "Jag kunde inte tolka modellens strukturerade svar. Försök igen."
            full_answer = safe_fallback
            structured_output_data = {
                "mode": "ASSIST",
                "saknas_underlag": False,
                "svar": safe_fallback,
                "kallor": [],
                "fakta_utan_kalla": [],
            }

    return {
        "answer": full_answer,
        "structured_data": structured_output_data,
        "revision_count": revision_count,
        "critic_ms": critic_ms,
        "critic_ok": critic_ok,
        "sources_cleared": sources_cleared,
    }
