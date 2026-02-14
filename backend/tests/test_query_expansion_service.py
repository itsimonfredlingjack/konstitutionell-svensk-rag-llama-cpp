import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.config_service import get_config_service
from app.services.query_expansion_service import QueryExpansionService


@pytest.mark.asyncio
async def test_expand_returns_three_queries_and_passes_grammar():
    config = get_config_service()
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(return_value=('["q1","q2","q3"]', None))

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("Vad säger GDPR om samtycke?")

    assert result.success is True
    assert result.queries == ["q1", "q2", "q3"]
    assert result.grammar_requested is True
    assert result.grammar_applied is True
    assert result.parsing_method == "json"

    _, kwargs = llm_service.chat_complete.call_args
    assert "grammar" in kwargs["config_override"]
    assert "root ::=" in kwargs["config_override"]["grammar"]


@pytest.mark.asyncio
async def test_expand_omits_grammar_when_disabled(monkeypatch):
    config = get_config_service()
    monkeypatch.setattr(config.settings, "query_expansion_use_grammar", False)
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(return_value=('["q1","q2","q3"]', None))

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("Vad säger GDPR om samtycke?")

    assert result.success is True
    assert result.grammar_requested is False
    assert result.grammar_applied is False
    _, kwargs = llm_service.chat_complete.call_args
    assert "grammar" not in kwargs["config_override"]


@pytest.mark.asyncio
async def test_expand_retries_without_grammar_on_llm_error(monkeypatch):
    config = get_config_service()
    monkeypatch.setattr(config.settings, "query_expansion_use_grammar", True)
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(
        side_effect=[
            RuntimeError("grammar unsupported"),
            ('["q1","q2","q3"]', None),
        ]
    )

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("Vad säger GDPR om samtycke?")

    assert result.success is True
    assert result.queries == ["q1", "q2", "q3"]
    assert llm_service.chat_complete.call_count == 2

    first_call = llm_service.chat_complete.call_args_list[0].kwargs["config_override"]
    second_call = llm_service.chat_complete.call_args_list[1].kwargs["config_override"]
    assert "grammar" in first_call
    assert "grammar" not in second_call


@pytest.mark.asyncio
async def test_expand_removes_duplicates_and_original_query():
    config = get_config_service()
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(
        return_value=('["GDPR samtycke","gdpr samtycke","personuppgifter"]', None)
    )

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("GDPR samtycke")

    assert result.success is True
    assert result.queries == ["personuppgifter"]


@pytest.mark.asyncio
async def test_expand_fallback_to_regex_parsing():
    config = get_config_service()
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(
        return_value=(
            'Här är förslag:\n["arbetsmiljörätt", "arbetsgivaransvar", "AML ansvar"]',
            None,
        )
    )

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("Vad gäller arbetsmiljölagen?")

    assert result.success is True
    assert result.queries == ["arbetsmiljörätt", "arbetsgivaransvar", "AML ansvar"]
    assert result.parsing_method == "regex"


@pytest.mark.asyncio
async def test_expand_fallback_to_split_parsing():
    config = get_config_service()
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(
        return_value=(
            "1. arbetsgivarens arbetsmiljöansvar enligt AML\n"
            "2) systematiskt arbetsmiljöarbete enligt AFS 2001:1\n"
            "3: arbetsmiljölagen 3 kap arbetsgivaransvar",
            None,
        )
    )

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("Vad gäller arbetsmiljölagen?")

    assert result.success is True
    assert result.queries == [
        "arbetsgivarens arbetsmiljöansvar enligt AML",
        "systematiskt arbetsmiljöarbete enligt AFS 2001:1",
        "arbetsmiljölagen 3 kap arbetsgivaransvar",
    ]
    assert result.parsing_method == "split"


@pytest.mark.asyncio
async def test_expand_fail_open_on_empty_output():
    config = get_config_service()
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(return_value=(" \n\t ", None))

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("Vad gäller OSL?")

    assert result.success is False
    assert result.queries == []
    assert result.error


@pytest.mark.asyncio
async def test_expand_respects_requested_count():
    config = get_config_service()
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(return_value=('["a","b","c"]', None))

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("test", count=2)

    assert result.success is True
    assert result.queries == ["a", "b"]


@pytest.mark.asyncio
async def test_expand_preserves_swedish_characters():
    config = get_config_service()
    llm_service = MagicMock()
    llm_service.chat_complete = AsyncMock(
        return_value=(
            '["arbetsmiljöåtgärder", "självständighetsprövning", "föräldraledighet och åtaganden"]',
            None,
        )
    )

    service = QueryExpansionService(config=config, llm_service=llm_service)
    result = await service.expand("Vad gäller arbetsmiljö?")

    assert result.success is True
    assert result.queries == [
        "arbetsmiljöåtgärder",
        "självständighetsprövning",
        "föräldraledighet och åtaganden",
    ]
