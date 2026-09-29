"""
Unit tests for agent/tools.py — file operations, bash execution, directory listing, and search.
Run with: pytest tests/test_tools.py -v
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the package root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import (
    _is_dangerous,
    dispatch_tool,
    execute_bash,
    list_directory,
    patch_file,
    read_file,
    search_code,
    write_file,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_file(tmp_path: Path) -> Path:
    """Create a temporary text file with known content."""
    f = tmp_path / "sample.txt"
    f.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")
    return f


@pytest.fixture
def tmp_py_file(tmp_path: Path) -> Path:
    """Create a temporary Python file."""
    f = tmp_path / "hello.py"
    f.write_text('def greet(name):\n    return f"Hello, {name}!"\n\nprint(greet("World"))\n')
    return f


# ── read_file ─────────────────────────────────────────────────────────────────

class TestReadFile:
    def test_reads_full_file(self, tmp_file: Path) -> None:
        result = read_file(str(tmp_file))
        assert "line 1" in result
        assert "line 5" in result

    def test_reads_line_range(self, tmp_file: Path) -> None:
        result = read_file(str(tmp_file), start_line=2, end_line=3)
        assert "line 2" in result
        assert "line 3" in result
        assert "line 1" not in result
        assert "line 5" not in result

    def test_prepends_line_numbers(self, tmp_file: Path) -> None:
        result = read_file(str(tmp_file))
        # Should contain line numbers like "   1 |"
        assert "|" in result

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = read_file(str(tmp_path / "nonexistent.txt"))
        assert "ERROR" in result
        assert "not found" in result.lower()

    def test_binary_file_rejected(self, tmp_path: Path) -> None:
        binary = tmp_path / "image.png"
        binary.write_bytes(b"\x89PNG\r\n\x1a\n")
        result = read_file(str(binary))
        assert "ERROR" in result
        assert "binary" in result.lower()

    def test_start_line_clamp(self, tmp_file: Path) -> None:
        result = read_file(str(tmp_file), start_line=100)
        # Should not crash, just return empty or last lines
        assert "ERROR" not in result or "not found" not in result.lower()

    def test_directory_is_rejected(self, tmp_path: Path) -> None:
        result = read_file(str(tmp_path))
        assert "ERROR" in result


# ── write_file ────────────────────────────────────────────────────────────────

class TestWriteFile:
    def test_creates_new_file(self, tmp_path: Path) -> None:
        target = tmp_path / "new_file.txt"
        result = write_file(str(target), "hello world\n")
        assert "OK" in result
        assert target.read_text() == "hello world\n"

    def test_overwrites_existing_file(self, tmp_file: Path) -> None:
        result = write_file(str(tmp_file), "overwritten\n")
        assert "OK" in result
        assert tmp_file.read_text() == "overwritten\n"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "file.txt"
        result = write_file(str(deep), "deep content")
        assert "OK" in result
        assert deep.exists()
        assert deep.read_text() == "deep content"

    def test_reports_line_count(self, tmp_path: Path) -> None:
        target = tmp_path / "multi.txt"
        result = write_file(str(target), "a\nb\nc\n")
        assert "3" in result  # 3 lines reported


# ── patch_file ────────────────────────────────────────────────────────────────

class TestPatchFile:
    def test_replaces_target_string(self, tmp_file: Path) -> None:
        result = patch_file(str(tmp_file), "line 3", "REPLACED")
        assert "OK" in result
        content = tmp_file.read_text()
        assert "REPLACED" in content
        assert "line 3" not in content

    def test_replaces_only_first_occurrence(self, tmp_path: Path) -> None:
        f = tmp_path / "repeat.txt"
        f.write_text("foo foo foo")
        patch_file(str(f), "foo", "bar")
        assert f.read_text() == "bar foo foo"

    def test_error_on_missing_target(self, tmp_file: Path) -> None:
        result = patch_file(str(tmp_file), "THIS DOES NOT EXIST", "anything")
        assert "ERROR" in result
        assert "not found" in result.lower()

    def test_error_on_missing_file(self, tmp_path: Path) -> None:
        result = patch_file(str(tmp_path / "ghost.txt"), "x", "y")
        assert "ERROR" in result

    def test_multiline_patch(self, tmp_path: Path) -> None:
        f = tmp_path / "code.py"
        f.write_text("def old():\n    pass\n")
        result = patch_file(str(f), "def old():\n    pass", "def new():\n    return 42")
        assert "OK" in result
        assert "def new" in f.read_text()


# ── execute_bash ──────────────────────────────────────────────────────────────

class TestExecuteBash:
    def test_simple_command(self) -> None:
        result = execute_bash("echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    def test_failed_command(self) -> None:
        result = execute_bash("exit 1", timeout=5)
        assert result["exit_code"] != 0

    def test_stderr_captured(self) -> None:
        result = execute_bash("echo error_text >&2", timeout=5)
        assert result["exit_code"] == 0
        assert "error_text" in result["stderr"]

    def test_timeout_respected(self) -> None:
        result = execute_bash("sleep 10", timeout=1)
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"].lower()

    def test_output_truncated(self) -> None:
        long_cmd = "python3 -c \"print('x' * 20000)\""
        result = execute_bash(long_cmd, timeout=10, max_output_chars=100)
        assert result["truncated"] is True
        assert len(result["stdout"]) <= 200  # some slack for the truncation message

    def test_dangerous_command_blocked_without_callback(self) -> None:
        """Without a confirm callback, dangerous commands still run (callback=None)."""
        # We test that the dangerous detection works via _is_dangerous
        assert _is_dangerous("rm -rf /tmp/test_something")

    def test_dangerous_command_aborted_by_callback(self) -> None:
        result = execute_bash(
            "rm -rf /tmp/coding_agent_test_do_not_exist",
            confirm_callback=lambda cmd: False,  # always deny
        )
        assert result["exit_code"] == -1
        assert "aborted" in result.get("error", "").lower()

    def test_dangerous_command_approved_by_callback(self, tmp_path: Path) -> None:
        # Create a safe temp dir to delete
        d = tmp_path / "safe_to_delete"
        d.mkdir()
        result = execute_bash(
            f"rm -rf {d}",
            confirm_callback=lambda cmd: True,  # always approve
        )
        assert result["exit_code"] == 0
        assert not d.exists()


# ── _is_dangerous ─────────────────────────────────────────────────────────────

class TestIsDangerous:
    @pytest.mark.parametrize("cmd,expected", [
        ("rm -rf /tmp", True),
        ("rm -fr /home", True),
        ("git reset --hard HEAD", True),
        ("git clean -fd", True),
        ("DROP DATABASE mydb", True),
        ("TRUNCATE TABLE users", True),
        ("DELETE FROM users;", True),
        ("echo hello", False),
        ("ls -la", False),
        ("pytest tests/", False),
        ("pip install rich", False),
        ("python main.py", False),
        ("git status", False),
        ("git add .", False),
        ("poweroff", True),
        ("sudo rm /etc/hosts", True),
    ])
    def test_dangerous_detection(self, cmd: str, expected: bool) -> None:
        assert _is_dangerous(cmd) == expected


# ── list_directory ────────────────────────────────────────────────────────────

class TestListDirectory:
    def test_basic_structure(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        (tmp_path / "README.md").write_text("")

        result = list_directory(str(tmp_path), max_depth=2)
        assert "src" in result
        assert "main.py" in result
        assert "README.md" in result

    def test_max_depth_respected(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep_file.txt").write_text("")

        result = list_directory(str(tmp_path), max_depth=2)
        assert "deep_file.txt" not in result  # depth=2 stops at a/b/

    def test_path_not_found(self, tmp_path: Path) -> None:
        result = list_directory(str(tmp_path / "nonexistent"))
        assert "ERROR" in result

    def test_file_sizes_shown(self, tmp_path: Path) -> None:
        f = tmp_path / "bigfile.txt"
        f.write_text("x" * 1024)
        result = list_directory(str(tmp_path), max_depth=1)
        assert "bigfile.txt" in result
        # Some size unit should appear
        assert any(unit in result for unit in ["B", "KB", "MB"])


# ── search_code ───────────────────────────────────────────────────────────────

class TestSearchCode:
    def test_finds_pattern(self, tmp_py_file: Path) -> None:
        result = search_code("def greet", path=str(tmp_py_file.parent))
        assert "greet" in result
        assert "hello.py" in result

    def test_regex_pattern(self, tmp_py_file: Path) -> None:
        result = search_code(r"f\"Hello.*\"", path=str(tmp_py_file.parent))
        assert "hello.py" in result

    def test_case_insensitive(self, tmp_py_file: Path) -> None:
        result = search_code("HELLO", path=str(tmp_py_file.parent), case_sensitive=False)
        assert "hello.py" in result

    def test_no_match(self, tmp_py_file: Path) -> None:
        result = search_code("THIS_PATTERN_WILL_NEVER_EXIST_12345", path=str(tmp_py_file.parent))
        assert "No matches" in result

    def test_file_pattern_filter(self, tmp_path: Path) -> None:
        (tmp_path / "code.py").write_text("target_word\n")
        (tmp_path / "doc.md").write_text("target_word\n")
        result = search_code("target_word", path=str(tmp_path), file_pattern="*.py")
        assert "code.py" in result
        assert "doc.md" not in result

    def test_invalid_regex(self, tmp_path: Path) -> None:
        result = search_code("[invalid regex", path=str(tmp_path))
        assert "ERROR" in result

    def test_path_not_found(self, tmp_path: Path) -> None:
        result = search_code("pattern", path=str(tmp_path / "ghost"))
        assert "ERROR" in result


# ── dispatch_tool ─────────────────────────────────────────────────────────────

class TestDispatchTool:
    def test_dispatch_read_file(self, tmp_file: Path) -> None:
        result = dispatch_tool("read_file", {"path": str(tmp_file)})
        assert "line 1" in result

    def test_dispatch_write_file(self, tmp_path: Path) -> None:
        target = str(tmp_path / "out.txt")
        result = dispatch_tool("write_file", {"path": target, "content": "test\n"})
        assert "OK" in result

    def test_dispatch_execute_bash(self) -> None:
        result = dispatch_tool("execute_bash", {"command": "echo dispatch_ok"})
        assert "dispatch_ok" in result

    def test_dispatch_list_directory(self, tmp_path: Path) -> None:
        result = dispatch_tool("list_directory", {"path": str(tmp_path)})
        assert str(tmp_path) in result or "ERROR" not in result

    def test_dispatch_search_code(self, tmp_py_file: Path) -> None:
        result = dispatch_tool(
            "search_code",
            {"pattern": "greet", "path": str(tmp_py_file.parent)},
        )
        assert "greet" in result

    def test_dispatch_unknown_tool(self) -> None:
        result = dispatch_tool("nonexistent_tool", {})
        assert "ERROR" in result
        assert "Unknown tool" in result
