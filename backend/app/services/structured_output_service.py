"""
Structured Output Service - JSON Schema Validation for Anti-Hallucination
Validates LLM responses against strict schema before showing to user
"""

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from ..utils.logging import get_logger

logger = get_logger(__name__)


class StructuredOutputSchema(BaseModel):
    """Schema for structured LLM output"""

    mode: str = Field(..., description="EVIDENCE or ASSIST")
    saknas_underlag: bool = Field(..., description="True if supporting documents missing")
    svar: str = Field(..., description="Answer text to show to user")
    kallor: List[Dict[str, str]] = Field(
        default_factory=list, description="Sources: [{doc_id, chunk_id, citat, loc}]"
    )
    fakta_utan_kalla: List[str] = Field(
        default_factory=list, description="Facts without sources (should be empty in EVIDENCE mode)"
    )
    arbetsanteckning: str = Field(
        default="", description="Internal control note (will be stripped from response)"
    )


class StructuredOutputService(BaseService):
    """
    Service for validating structured LLM output.

    Features:
    - JSON schema validation
    - Citation enforcement (check that all facts have sources in EVIDENCE mode)
    - Anti-hallucination checks (no facts without sources in EVIDENCE)
    - Strip internal notes before returning to user
    """

    def __init__(self, config: ConfigService):
        super().__init__(config)
        self.logger.info("Structured Output Service initialized")

    async def initialize(self) -> None:
        self._mark_initialized()

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        self._mark_uninitialized()

    def validate_output(
        self, json_output: Dict[str, Any], mode: str
    ) -> tuple[bool, List[str], Optional[StructuredOutputSchema]]:
        """
        Validate structured output against schema and mode-specific rules.

        Args:
            json_output: LLM response as JSON
            mode: Response mode (EVIDENCE or ASSIST)

        Returns:
            Tuple of (is_valid, errors_list, validated_schema)
        """
        errors = []

        # Step 1: Pydantic schema validation
        try:
            validated = StructuredOutputSchema(**json_output)
        except ValidationError as e:
            errors.extend([f"Schema validation error: {err['msg']}" for err in e.errors()])
            self.logger.error(f"Schema validation failed: {errors}")
            return False, errors, None

        # Step 2: Mode-specific validation
        if mode.upper() == "EVIDENCE":
            # EVIDENCE: fakta_utan_kalla MUST be empty
            if validated.fakta_utan_kalla:
                errors.append(
                    f"EVIDENCE mode: {len(validated.fakta_utan_kalla)} facts without sources. "
                    "In EVIDENCE mode, all facts MUST have sources."
                )

            # EVIDENCE: If saknas_underlag=true, svar should be refusal
            if validated.saknas_underlag:
                # Check if svar matches refusal pattern
                refusal_pattern = r"Tyvärr kan jag inte besvara frågan"
                if not re.search(refusal_pattern, validated.svar):
                    errors.append("EVIDENCE mode: If saknas_underlag=true, svar must be refusal.")

        elif mode.upper() == "ASSIST":
            # ASSIST: Fakta från dokument ska ha källa; allmän kunskap i fakta_utan_källa
            # This is more lenient - we just log a warning if facts without sources exist
            if validated.fakta_utan_kalla:
                self.logger.info(
                    f"ASSIST mode: {len(validated.fakta_utan_kalla)} facts without sources "
                    "(allowed for general knowledge)"
                )

        is_valid = len(errors) == 0

        if not is_valid:
            self.logger.warning(f"Structured output validation failed: {errors}")
        else:
            self.logger.info("Structured output validation passed")

        return is_valid, errors, validated

    def strip_internal_note(self, schema: StructuredOutputSchema) -> Dict[str, Any]:
        """
        Strip internal notes before returning to user.

        Args:
            schema: Validated structured output schema

        Returns:
            Cleaned dict without internal notes
        """
        return {
            "mode": schema.mode,
            "saknas_underlag": schema.saknas_underlag,
            "svar": schema.svar,
            "kallor": schema.kallor,
            "fakta_utan_kalla": schema.fakta_utan_kalla,
            # arbetsanteckning is NOT included (security/privacy)
        }

    def parse_llm_json(self, text: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response, handling markdown code fences.

        Args:
            text: LLM response text

        Returns:
            Parsed JSON dict

        Raises:
            json.JSONDecodeError: If text cannot be parsed as JSON
        """
        # Strip markdown code fences if present
        json_text = text.strip()
        if json_text.startswith("```json"):
            json_text = json_text[7:]
        if json_text.startswith("```"):
            json_text = json_text[3:]
        if json_text.endswith("```"):
            json_text = json_text[:-3]
        json_text = json_text.strip()

        return json.loads(json_text)

    async def validate_with_retries(
        self, llm_call_fn, mode: str, max_retries: int = 2, retry_instruction: str = None
    ) -> tuple[bool, List[str], Optional[StructuredOutputSchema], bool]:
        """
        Validate structured output with retry logic (max 2 attempts).

        Args:
            llm_call_fn: Async function that returns LLM response text
            mode: Response mode (EVIDENCE or ASSIST)
            max_retries: Maximum retry attempts (default: 2)
            retry_instruction: Optional instruction for retry attempt

        Returns:
            Tuple of (is_valid, errors, validated_schema, is_retry_attempt)
        """

        # Attempt 1: Normal structured output
        try:
            first_attempt_text = await llm_call_fn()
            json_output = self.parse_llm_json(first_attempt_text)
            is_valid, errors, validated = self.validate_output(json_output, mode)

            if is_valid and validated:
                return True, [], validated, False  # Success on first attempt
            else:
                # Validation failed, will retry
                pass

        except json.JSONDecodeError as e:
            # JSON parsing failed on first attempt
            is_valid, errors, validated = False, [f"JSON parse error: {str(e)}"], None

        # Retry attempts
        for attempt in range(1, max_retries):
            try:
                if retry_instruction:
                    # Add retry instruction to the LLM call
                    retry_text = await llm_call_fn(retry_instruction=retry_instruction)
                else:
                    retry_text = await llm_call_fn()

                json_output = self.parse_llm_json(retry_text)
                is_valid, errors, validated = self.validate_output(json_output, mode)

                if is_valid and validated:
                    return True, [], validated, True  # Success on retry attempt

            except json.JSONDecodeError as e:
                # JSON parsing failed on retry
                is_valid, errors, validated = (
                    False,
                    [f"JSON parse error on retry {attempt}: {str(e)}"],
                    None,
                )
                # Continue to next retry
                continue

        # All attempts failed
        return False, errors or ["All retry attempts failed"], None, True


@lru_cache()
def get_structured_output_service(
    config: Optional[ConfigService] = None,
) -> StructuredOutputService:
    if config is None:
        config = get_config_service()

    return StructuredOutputService(config)
