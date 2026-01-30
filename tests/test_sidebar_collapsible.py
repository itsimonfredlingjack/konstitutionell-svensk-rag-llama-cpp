import pytest

from vibe_cli.config import Config
from vibe_cli.models.messages import ToolResult
from vibe_cli.ui.app import VibeApp
from vibe_cli.ui.project_tree import FilePinMessage


class DummyProvider:
    def __init__(self, model: str = "test-model") -> None:
        self.model = model

    async def get_available_models(self) -> list[str]:
        return [self.model]


@pytest.mark.asyncio
async def test_sidebar_collapsible_sections_present(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_cli.ui.app.Config.load", lambda *args, **kwargs: Config())
    monkeypatch.setattr("vibe_cli.ui.app.build_provider", lambda *args, **kwargs: DummyProvider())

    app = VibeApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#sidebar-project")
        app.query_one("#sidebar-pinned")
        app.query_one("#sidebar-system")
        app.query_one("#sidebar-log")


@pytest.mark.asyncio
async def test_pin_expands_pinned_section(monkeypatch, tmp_path):
    (tmp_path / "x.txt").write_text("hello")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_cli.ui.app.Config.load", lambda *args, **kwargs: Config())
    monkeypatch.setattr("vibe_cli.ui.app.build_provider", lambda *args, **kwargs: DummyProvider())

    app = VibeApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        pinned = app.query_one("#sidebar-pinned")
        assert pinned.collapsed is True

        await app.on_file_pin_message(FilePinMessage(tmp_path / "x.txt"))
        await pilot.pause()
        assert app.query_one("#sidebar-pinned").collapsed is False


@pytest.mark.asyncio
async def test_tool_error_expands_log_section(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vibe_cli.ui.app.Config.load", lambda *args, **kwargs: Config())
    monkeypatch.setattr("vibe_cli.ui.app.build_provider", lambda *args, **kwargs: DummyProvider())

    app = VibeApp()

    async def fake_run(_text: str):
        yield ToolResult(tool_call_id="1", content="boom", is_error=True, tool_name="run_command")

    app.agent.run = fake_run  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#sidebar-log").collapsed is True
        await app.process("trigger error")
        await pilot.pause()
        assert app.query_one("#sidebar-log").collapsed is False
