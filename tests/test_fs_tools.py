
import pytest

from vibe_cli.tools.filesystem import ReadFileTool, WriteFileTool


@pytest.mark.asyncio
async def test_read_write_file(tmp_path):
    workspace = tmp_path

    # Write
    write_tool = WriteFileTool(workspace)
    result = await write_tool.execute(path="test.txt", content="Hello\nWorld")
    assert not result.is_error
    assert (workspace / "test.txt").read_text() == "Hello\nWorld"

    # Read
    read_tool = ReadFileTool(workspace)
    result = await read_tool.execute(path="test.txt")
    assert not result.is_error
    assert "Hello" in result.content
    assert "World" in result.content
    assert "   1 │ Hello" in result.content

@pytest.mark.asyncio
async def test_path_traversal(tmp_path):
    workspace = tmp_path
    (workspace / "safe.txt").touch()

    # Try to read outside
    tool = ReadFileTool(workspace)
    result = await tool.execute(path="../unsafe.txt")
    assert result.is_error
    assert "escapes workspace" in result.content
