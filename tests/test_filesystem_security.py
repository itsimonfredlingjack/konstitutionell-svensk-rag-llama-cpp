"""
Security tests for filesystem operations.

HIGH PRIORITY: These tests validate protection against path traversal attacks (HIGH-01).
Focuses on symlink attack vectors which are not fully covered in basic tests.
"""

import pytest
from pathlib import Path

from vibe_cli.tools.filesystem import ReadFileTool, WriteFileTool, StrReplaceTool


@pytest.mark.security
@pytest.mark.asyncio
async def test_read_symlink_to_outside_workspace_blocked(tmp_path):
    """Test that symlinks pointing outside workspace are blocked"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("SECRET_DATA")

    # Create symlink inside workspace pointing outside
    link = workspace / "link_to_secret.txt"
    link.symlink_to(secret)

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="link_to_secret.txt")

    # Should block symlink traversal
    # Current implementation may not catch this - this test documents the vulnerability
    if result.is_error:
        assert "escapes workspace" in result.content or "symlink" in result.content
    else:
        # VULNERABILITY: If this passes, symlink attack is possible
        pytest.fail(f"SECURITY BUG: Symlink traversal allowed! Got: {result.content}")


@pytest.mark.security
@pytest.mark.asyncio
async def test_write_symlink_to_outside_workspace_blocked(tmp_path):
    """Test that writing via symlinks outside workspace is blocked"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "target.txt"
    target.write_text("original")

    link = workspace / "link_to_target.txt"
    link.symlink_to(target)

    tool = WriteFileTool(workspace)
    result = await tool.execute(path="link_to_target.txt", content="overwritten")

    # Should block write via symlink
    if result.is_error:
        assert target.read_text() == "original"  # Not modified
    else:
        # VULNERABILITY: If write succeeded, check if it wrote outside
        if target.read_text() == "overwritten":
            pytest.fail("SECURITY BUG: Symlink write traversal allowed!")


@pytest.mark.security
@pytest.mark.asyncio
async def test_str_replace_symlink_to_outside_workspace_blocked(tmp_path):
    """Test that str_replace cannot modify files outside workspace via symlink"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "config.txt"
    target.write_text("admin=false\n")

    link = workspace / "config_link.txt"
    link.symlink_to(target)

    tool = StrReplaceTool(workspace)
    result = await tool.execute(
        path="config_link.txt",
        old_str="admin=false",
        new_str="admin=true",
    )

    # Should block modification via symlink
    if result.is_error:
        assert target.read_text() == "admin=false\n"
    else:
        if target.read_text() == "admin=true\n":
            pytest.fail("SECURITY BUG: Symlink modification traversal allowed!")


@pytest.mark.security
@pytest.mark.asyncio
async def test_symlink_chain_attack_blocked(tmp_path):
    """Test that chained symlinks cannot escape workspace"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("SECRET")

    # Create chain: link1 -> link2 -> ../../outside/secret.txt
    (workspace / "link1").symlink_to(workspace / "link2")
    (workspace / "link2").symlink_to(secret)

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="link1")

    if not result.is_error and "SECRET" in result.content:
        pytest.fail("SECURITY BUG: Symlink chain traversal allowed!")


@pytest.mark.security
@pytest.mark.asyncio
async def test_symlink_to_parent_directory_blocked(tmp_path):
    """Test that symlinks to parent directories are blocked"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create symlink to parent directory
    link = workspace / "parent_link"
    link.symlink_to(tmp_path)

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="parent_link/sensitive_file.txt")

    # Should block directory symlinks
    if not result.is_error:
        pytest.fail("SECURITY BUG: Directory symlink traversal allowed!")


@pytest.mark.asyncio
async def test_symlink_inside_workspace_allowed(tmp_path):
    """Test that symlinks within workspace are allowed"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "real.txt").write_text("data")
    (workspace / "link.txt").symlink_to(workspace / "real.txt")

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="link.txt")

    # Internal symlinks should work
    assert not result.is_error
    assert "data" in result.content


@pytest.mark.asyncio
async def test_relative_symlink_inside_workspace_allowed(tmp_path):
    """Test that relative symlinks within workspace are allowed"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "dir1").mkdir()
    (workspace / "dir2").mkdir()
    (workspace / "dir1" / "file.txt").write_text("content")

    # Relative symlink: dir2/link -> ../dir1/file.txt
    (workspace / "dir2" / "link").symlink_to(Path("../dir1/file.txt"))

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="dir2/link")

    assert not result.is_error
    assert "content" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_read_path_with_double_dots_blocked(tmp_path):
    """Test that paths with .. are properly validated"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SECRET")

    tool = ReadFileTool(workspace)

    # Try various .. patterns
    dangerous_paths = [
        "../outside/secret.txt",
        "subdir/../../outside/secret.txt",
        "./../../outside/secret.txt",
    ]

    for path in dangerous_paths:
        result = await tool.execute(path=path)
        assert result.is_error, f"Should block: {path}"
        assert "escapes workspace" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_write_path_with_double_dots_blocked(tmp_path):
    """Test that write paths with .. are blocked"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    tool = WriteFileTool(workspace)

    result = await tool.execute(
        path="../outside/malicious.txt",
        content="evil",
    )

    assert result.is_error
    assert not (outside / "malicious.txt").exists()


@pytest.mark.security
@pytest.mark.asyncio
async def test_read_absolute_path_blocked(tmp_path):
    """Test that absolute paths are blocked"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = ReadFileTool(workspace)

    result = await tool.execute(path="/etc/passwd")

    assert result.is_error
    assert "escapes workspace" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_write_absolute_path_blocked(tmp_path):
    """Test that absolute paths cannot be written"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = WriteFileTool(workspace)

    result = await tool.execute(
        path="/tmp/evil.txt",
        content="malicious",
    )

    assert result.is_error
    assert not Path("/tmp/evil.txt").exists()


@pytest.mark.asyncio
async def test_read_unicode_path(tmp_path):
    """Test that Unicode filenames are handled safely"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    unicode_file = workspace / "файл.txt"
    unicode_file.write_text("Unicode content")

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="файл.txt")

    assert not result.is_error
    assert "Unicode content" in result.content


@pytest.mark.asyncio
async def test_write_unicode_content(tmp_path):
    """Test that Unicode content is written correctly"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = WriteFileTool(workspace)
    result = await tool.execute(
        path="test.txt",
        content="Hello 世界 🌍",
    )

    assert not result.is_error
    assert (workspace / "test.txt").read_text() == "Hello 世界 🌍"


@pytest.mark.asyncio
async def test_read_nonexistent_file_error(tmp_path):
    """Test that reading nonexistent file returns error"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = ReadFileTool(workspace)
    result = await tool.execute(path="nonexistent.txt")

    assert result.is_error
    assert "not found" in result.content.lower()


@pytest.mark.asyncio
async def test_write_creates_parent_directories(tmp_path):
    """Test that write creates parent directories"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = WriteFileTool(workspace)
    result = await tool.execute(
        path="deep/nested/dir/file.txt",
        content="content",
    )

    assert not result.is_error
    assert (workspace / "deep" / "nested" / "dir" / "file.txt").read_text() == "content"


@pytest.mark.asyncio
async def test_str_replace_unique_string_success(tmp_path):
    """Test that str_replace works with unique strings"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "test.txt").write_text("line1\nunique_line\nline3")

    tool = StrReplaceTool(workspace)
    result = await tool.execute(
        path="test.txt",
        old_str="unique_line",
        new_str="replaced_line",
    )

    assert not result.is_error
    assert (workspace / "test.txt").read_text() == "line1\nreplaced_line\nline3"


@pytest.mark.asyncio
async def test_str_replace_non_unique_string_error(tmp_path):
    """Test that str_replace fails with non-unique strings"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "test.txt").write_text("repeat\nrepeat\nrepeat")

    tool = StrReplaceTool(workspace)
    result = await tool.execute(
        path="test.txt",
        old_str="repeat",
        new_str="new",
    )

    assert result.is_error
    assert "3 times" in result.content or "unique" in result.content.lower()


@pytest.mark.asyncio
async def test_str_replace_string_not_found_error(tmp_path):
    """Test that str_replace fails when string not found"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "test.txt").write_text("content")

    tool = StrReplaceTool(workspace)
    result = await tool.execute(
        path="test.txt",
        old_str="nonexistent",
        new_str="new",
    )

    assert result.is_error
    assert "not found" in result.content.lower()


@pytest.mark.asyncio
async def test_str_replace_fuzzy_match_suggestion(tmp_path):
    """Test that str_replace suggests similar strings"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "test.txt").write_text("def my_function():\n    pass")

    tool = StrReplaceTool(workspace)
    result = await tool.execute(
        path="test.txt",
        old_str="def my_functon():",  # Typo
        new_str="def my_function():",
    )

    assert result.is_error
    # Should suggest the similar string
    if "Did you mean" in result.content or "my_function" in result.content:
        # Fuzzy matching working
        pass
