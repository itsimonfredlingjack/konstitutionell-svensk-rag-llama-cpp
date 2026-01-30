from vibe_cli.config import ProviderConfig
from vibe_cli.providers.base import LLMProvider
from vibe_cli.providers.ollama import OllamaProvider
from vibe_cli.providers.openai_compat import OpenAICompatProvider
from vibe_cli.providers.opencode import OpenCodeProvider


def build_provider(config: ProviderConfig | None) -> LLMProvider:
    if config is None:
        return OllamaProvider()

    if config.type == "opencode":
        return OpenCodeProvider(model=config.model)

    if config.type == "ollama":
        return OllamaProvider(
            base_url=config.base_url or "http://localhost:11434",
            model=config.model,
            auto_switch=config.auto_switch,
            small_model=config.small_model,
            large_model=config.large_model,
            switch_tokens=config.switch_tokens,
            switch_keywords=config.switch_keywords,
            keep_alive=config.keep_alive,
        )

    return OpenAICompatProvider(
        base_url=config.base_url or "https://api.openai.com/v1",
        api_key=config.api_key,
        model=config.model,
        auto_switch=config.auto_switch,
        small_model=config.small_model,
        large_model=config.large_model,
        switch_tokens=config.switch_tokens,
        switch_keywords=config.switch_keywords,
    )
