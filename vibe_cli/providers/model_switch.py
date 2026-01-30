from collections.abc import Iterable
from typing import Callable

from vibe_cli.models.messages import Message


def select_model_for_messages(
    messages: list[Message],
    default_model: str,
    auto_switch: bool,
    small_model: str | None,
    large_model: str | None,
    token_threshold: int,
    keywords: Iterable[str] | None,
    token_counter: Callable[[str], int] | None = None,
) -> str:
    if not auto_switch or not small_model or not large_model:
        return default_model

    prompt_text = _flatten_messages(messages)
    if not prompt_text:
        return small_model

    token_count = token_counter(prompt_text) if token_counter else _estimate_tokens(prompt_text)
    keyword_hit = _contains_keywords(prompt_text, keywords or [])

    if token_count >= token_threshold or keyword_hit:
        return large_model
    return small_model


def _flatten_messages(messages: list[Message]) -> str:
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg.content, str):
            parts.append(msg.content)
            continue
        for item in msg.content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(text)
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _contains_keywords(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)
