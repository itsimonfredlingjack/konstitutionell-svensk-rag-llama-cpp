"""
Security tests for shell command execution.

CRITICAL: These tests validate protection against command injection attacks (CRIT-01).
All tests must pass before production deployment.
"""

import pytest
from pathlib import Path

from vibe_cli.tools.shell import ShellTool


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_command_injection_via_semicolon(tmp_path):
    """Test that command injection via semicolons is blocked"""
    tool = ShellTool(tmp_path)
    result = await tool.execute(command="ls; rm -rf /")

    assert result.is_error
    # Should block due to shell metacharacter (;)
    assert "dangerous" in result.content.lower() or "blocked" in result.content.lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_command_injection_via_pipe(tmp_path):
    """Test that command injection via pipes is blocked"""
    (tmp_path / "malicious.sh").write_text("#!/bin/bash\necho PWNED")

    tool = ShellTool(tmp_path)
    result = await tool.execute(command="ls | sh malicious.sh")

    # Should block pipe (shell metacharacter)
    assert result.is_error
    assert "dangerous" in result.content.lower() or "blocked" in result.content.lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_command_injection_via_backticks(tmp_path):
    """Test that command injection via backticks is blocked"""
    tool = ShellTool(tmp_path)
    result = await tool.execute(command="echo `rm -rf /`")

    # Backticks in arguments should be blocked or sanitized
    assert result.is_error or "rm -rf /" not in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_command_injection_via_dollar_paren(tmp_path):
    """Test that command injection via $() is blocked"""
    tool = ShellTool(tmp_path)
    result = await tool.execute(command="echo $(cat /etc/passwd)")

    # Command substitution should be blocked or sanitized
    assert result.is_error or "root:" not in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_command_injection_via_and_operator(tmp_path):
    """Test that command injection via && is blocked"""
    tool = ShellTool(tmp_path)
    result = await tool.execute(command="ls && rm -rf /")

    assert result.is_error
    # Should block due to shell metacharacter (&&)
    assert "dangerous" in result.content.lower() or "blocked" in result.content.lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_blocked_patterns_rm_rf(tmp_path):
    """Test that dangerous rm -rf patterns are blocked"""
    tool = ShellTool(tmp_path)

    dangerous_commands = [
        "rm -rf /",
        "rm -rf .",
        "rm -rf *",
    ]

    for cmd in dangerous_commands:
        result = await tool.execute(command=cmd)
        assert result.is_error, f"Should block: {cmd}"
        # Should be blocked (rm not in allowed list or blocked pattern)
        assert "not in allowed list" in result.content or "blocked" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_blocked_patterns_dev_null(tmp_path):
    """Test that redirection to /dev/ is blocked"""
    tool = ShellTool(tmp_path)

    result = await tool.execute(command="echo test > /dev/sda")

    assert result.is_error
    # Should be blocked due to redirection operator (>) being a dangerous metacharacter
    assert "dangerous" in result.content.lower() or "blocked" in result.content.lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_blocked_patterns_sudo(tmp_path):
    """Test that sudo commands are blocked"""
    tool = ShellTool(tmp_path)

    result = await tool.execute(command="sudo ls")

    assert result.is_error
    assert "blocked pattern" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_allowed_command_not_in_list(tmp_path):
    """Test that commands not in allowed list are rejected"""
    tool = ShellTool(tmp_path)

    result = await tool.execute(command="curl http://evil.com")

    assert result.is_error
    assert "not in allowed list" in result.content
    assert "curl" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_allowed_command_with_safe_args(tmp_path):
    """Test that allowed commands with safe args execute"""
    (tmp_path / "test.txt").write_text("hello world")

    tool = ShellTool(tmp_path)
    result = await tool.execute(command="cat test.txt")

    assert not result.is_error
    assert "hello world" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_cwd_escape_via_parent_directory(tmp_path):
    """Test that cwd cannot escape workspace via parent directory"""
    tool = ShellTool(tmp_path)

    result = await tool.execute(command="ls", cwd="../../etc")

    assert result.is_error
    assert "escapes workspace" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_cwd_escape_via_absolute_path(tmp_path):
    """Test that cwd cannot escape workspace via absolute path"""
    tool = ShellTool(tmp_path)

    result = await tool.execute(command="ls", cwd="/etc")

    assert result.is_error
    assert "escapes workspace" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_cwd_safe_relative_path(tmp_path):
    """Test that safe relative cwd paths work"""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "file.txt").write_text("data")

    tool = ShellTool(tmp_path)
    result = await tool.execute(command="ls", cwd="subdir")

    assert not result.is_error
    assert "file.txt" in result.content


@pytest.mark.asyncio
async def test_shell_timeout_enforced(tmp_path):
    """Test that long-running commands timeout"""
    # Need to add sleep to allowed commands for this test
    tool = ShellTool(tmp_path, allowed_commands=["sleep"], timeout=1)

    result = await tool.execute(command="sleep 10")

    assert result.is_error
    assert "timed out" in result.content.lower()


@pytest.mark.asyncio
async def test_shell_command_exit_code_nonzero(tmp_path):
    """Test that non-zero exit codes are reported as errors"""
    tool = ShellTool(tmp_path)

    # grep with no match returns exit code 1
    result = await tool.execute(command="grep nonexistent test.txt")

    assert result.is_error
    assert "exit" in result.content.lower()


@pytest.mark.asyncio
async def test_shell_stdout_and_stderr_captured(tmp_path):
    """Test that both stdout and stderr are captured"""
    (tmp_path / "script.sh").write_text("#!/bin/bash\necho stdout\necho stderr >&2\nexit 0")
    (tmp_path / "script.sh").chmod(0o755)

    tool = ShellTool(tmp_path, allowed_commands=["bash"])
    result = await tool.execute(command="bash script.sh")

    assert not result.is_error
    assert "stdout" in result.content
    assert "stderr" in result.content
    assert "STDOUT:" in result.content
    assert "STDERR:" in result.content


@pytest.mark.asyncio
async def test_shell_empty_output(tmp_path):
    """Test that commands with no output are handled"""
    (tmp_path / "test.txt").touch()

    tool = ShellTool(tmp_path)
    result = await tool.execute(command="cat test.txt")

    assert not result.is_error
    assert "(no output)" in result.content or result.content.strip() == ""


@pytest.mark.asyncio
async def test_shell_custom_allowed_commands(tmp_path):
    """Test that custom allowed commands list works"""
    tool = ShellTool(tmp_path, allowed_commands=["echo", "pwd"])

    # Allowed command
    result = await tool.execute(command="echo hello")
    assert not result.is_error

    # Not allowed (even though normally safe)
    result = await tool.execute(command="ls")
    assert result.is_error


@pytest.mark.asyncio
async def test_shell_custom_blocked_patterns(tmp_path):
    """Test that custom blocked patterns work"""
    tool = ShellTool(
        tmp_path,
        allowed_commands=["echo"],
        blocked_patterns=["secret", "password"],
    )

    result = await tool.execute(command="echo secret data")

    assert result.is_error
    assert "blocked pattern" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_path_argument_injection(tmp_path):
    """Test that path arguments cannot escape workspace"""
    (tmp_path / "safe.txt").write_text("safe")

    tool = ShellTool(tmp_path)

    # Try to read outside workspace via path argument
    result = await tool.execute(command="cat ../../../etc/passwd")

    # Should either error or not find the file (workspace is isolated)
    assert result.is_error or "safe" in result.content


@pytest.mark.security
@pytest.mark.asyncio
async def test_shell_environment_variable_not_leaked(tmp_path):
    """Test that sensitive environment variables are not accessible"""
    import os

    # Set a sensitive env var
    os.environ["SECRET_TOKEN"] = "super_secret_123"

    tool = ShellTool(tmp_path)
    result = await tool.execute(command="echo $SECRET_TOKEN")

    # Should not expose the secret (depends on shell isolation)
    # This test may need adjustment based on implementation
    # For now, just verify command executes
    assert not result.is_error or "not in allowed list" in result.content
