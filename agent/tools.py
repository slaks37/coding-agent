"""
Tool implementations: file I/O, bash execution, directory listing, and code search.
All functions return plain strings (or dicts) suitable for feeding back to the LLM.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Optional

# ── Helpers ───────────────────────────────────────────────────────────────────

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".wav",
    ".pyc", ".pyo", ".class",
    ".db", ".sqlite", ".sqlite3",
}

DANGEROUS_PATTERNS = [
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f",   # rm -rf or rm -fr
    r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r",
    r"\bdd\b.*\bof=",                   # dd of=...
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-[a-zA-Z]*f",
    r":(){:|:&};:",                      # fork bomb
    r"mkfs\.",                           # format filesystem
    r">\s*/dev/sd",                      # overwrite disk
    r"DROP\s+(DATABASE|TABLE|SCHEMA)",  # SQL drops
    r"TRUNCATE\s+TABLE",
    r"DELETE\s+FROM\s+\w+\s*;?\s*$",   # DELETE without WHERE
    r"chmod\s+-[a-zA-Z]*R.*777",        # recursive 777
    r"sudo\s+rm",
    r"poweroff|shutdown|reboot|halt",
]


def _is_dangerous(command: str) -> bool:
    """Return True if the command matches any dangerous pattern."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def _resolve(path: str) -> Path:
    return Path(path).expanduser()


# ── Tool Functions ─────────────────────────────────────────────────────────────


def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """
    Read file contents, optionally restricted to a line range.
    Returns the file content as a string with line numbers prepended.
    """
    p = _resolve(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    if not p.is_file():
        return f"ERROR: Path is not a file: {path}"
    if p.suffix.lower() in BINARY_EXTENSIONS:
        return f"ERROR: Binary file, cannot read as text: {path}"

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"ERROR reading file: {exc}"

    lines = content.splitlines(keepends=True)
    total = len(lines)

    s = (start_line or 1) - 1          # convert to 0-based
    e = (end_line or total)             # end is inclusive 1-based → exclusive 0-based

    s = max(0, min(s, total))
    e = max(s, min(e, total))

    selected = lines[s:e]
    numbered = "".join(f"{s + i + 1:4d} | {line}" for i, line in enumerate(selected))
    header = f"File: {path} (lines {s+1}–{e} of {total})\n{'─'*60}\n"
    return header + numbered


def write_file(path: str, content: str) -> str:
    """
    Create or overwrite a file with the given content.
    Parent directories are created automatically.
    """
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"OK: Wrote {lines} lines ({len(content)} bytes) to {path}"
    except Exception as exc:
        return f"ERROR writing file: {exc}"


def patch_file(path: str, target_string: str, replacement_string: str) -> str:
    """
    Replace the first occurrence of target_string in the file with replacement_string.
    """
    p = _resolve(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    try:
        original = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"ERROR reading file: {exc}"

    if target_string not in original:
        # Try to give a helpful snippet for debugging
        return (
            f"ERROR: target_string not found in {path}.\n"
            f"  Target (first 200 chars): {repr(target_string[:200])}"
        )

    patched = original.replace(target_string, replacement_string, 1)
    try:
        p.write_text(patched, encoding="utf-8")
    except Exception as exc:
        return f"ERROR writing patched file: {exc}"

    return f"OK: Patched {path} (replaced {len(target_string)} chars with {len(replacement_string)} chars)"


def execute_bash(
    command: str,
    timeout: int = 30,
    max_output_chars: int = 8000,
    confirm_callback=None,
) -> dict:
    """
    Execute a shell command and return stdout, stderr, and exit_code.

    Args:
        command: Shell command string.
        timeout: Seconds before the process is killed.
        max_output_chars: Maximum characters captured per stream.
        confirm_callback: Optional callable(command) -> bool for dangerous commands.

    Returns:
        dict with keys: stdout, stderr, exit_code, truncated
    """
    if _is_dangerous(command):
        if confirm_callback is not None:
            approved = confirm_callback(command)
            if not approved:
                return {
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                    "truncated": False,
                    "error": f"Command aborted by user: {command}",
                }
        # If no callback, still warn but proceed (caller handles it)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        truncated = False

        if len(stdout) > max_output_chars:
            stdout = stdout[:max_output_chars] + f"\n... [truncated, {len(result.stdout)} chars total]"
            truncated = True
        if len(stderr) > max_output_chars:
            stderr = stderr[:max_output_chars] + f"\n... [truncated, {len(result.stderr)} chars total]"
            truncated = True

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
            "truncated": truncated,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"ERROR: Command timed out after {timeout} seconds.",
            "exit_code": -1,
            "truncated": False,
        }
    except Exception as exc:
        return {
            "stdout": "",
            "stderr": f"ERROR executing command: {exc}",
            "exit_code": -1,
            "truncated": False,
        }


def list_directory(path: str = ".", max_depth: int = 2) -> str:
    """
    Return a formatted directory tree up to max_depth levels deep.
    """
    root = _resolve(path)
    if not root.exists():
        return f"ERROR: Path not found: {path}"
    if not root.is_dir():
        return f"ERROR: Not a directory: {path}"

    lines: list[str] = [str(root) + "/"]
    _walk_tree(root, "", max_depth, 0, lines)

    return "\n".join(lines)


def _walk_tree(
    directory: Path,
    prefix: str,
    max_depth: int,
    current_depth: int,
    lines: list[str],
) -> None:
    if current_depth >= max_depth:
        return

    try:
        entries = sorted(directory.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        lines.append(prefix + "    [Permission denied]")
        return

    # Filter out __pycache__ and .git internals for clarity
    skip = {"__pycache__", ".git", ".mypy_cache", ".pytest_cache", "node_modules", ".venv", "venv"}
    entries = [e for e in entries if e.name not in skip]

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        if entry.is_dir():
            lines.append(prefix + connector + entry.name + "/")
            _walk_tree(entry, prefix + extension, max_depth, current_depth + 1, lines)
        else:
            size = entry.stat().st_size
            size_str = _human_size(size)
            lines.append(prefix + connector + entry.name + f"  [{size_str}]")


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size //= 1024
    return f"{size:.0f} TB"


def search_code(
    pattern: str,
    path: str = ".",
    file_pattern: Optional[str] = None,
    case_sensitive: bool = True,
    max_results: int = 200,
) -> str:
    """
    Search for a text/regex pattern across all files under path.
    Returns matching lines with file:line:content format.
    """
    root = _resolve(path)
    if not root.exists():
        return f"ERROR: Path not found: {path}"

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        return f"ERROR: Invalid regex pattern: {exc}"

    results: list[str] = []
    files_searched = 0
    files_matched = 0

    search_paths: list[Path] = []
    if root.is_file():
        search_paths = [root]
    else:
        for p in root.rglob("*"):
            if p.is_file():
                if file_pattern and not fnmatch.fnmatch(p.name, file_pattern):
                    continue
                if p.suffix.lower() in BINARY_EXTENSIONS:
                    continue
                # Skip hidden dirs
                if any(part.startswith(".") for part in p.relative_to(root).parts[:-1]):
                    continue
                search_paths.append(p)

    for p in sorted(search_paths):
        files_searched += 1
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        matched_lines = []
        for lineno, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                matched_lines.append(f"  {lineno:4d}: {line.rstrip()}")
                if len(results) + len(matched_lines) >= max_results:
                    break

        if matched_lines:
            files_matched += 1
            rel = p.relative_to(root) if p.is_relative_to(root) else p
            results.append(f"\n{rel}")
            results.extend(matched_lines)

        if len(results) >= max_results:
            results.append(f"\n... [results truncated at {max_results}]")
            break

    if not results:
        return f"No matches found for pattern '{pattern}' in {path} ({files_searched} files searched)"

    header = f"Pattern: '{pattern}' — {files_matched} file(s) matched of {files_searched} searched\n"
    return header + "\n".join(results)


# ── Dispatch helper ───────────────────────────────────────────────────────────

def dispatch_tool(
    tool_name: str,
    tool_args: dict,
    bash_timeout: int = 30,
    max_output_chars: int = 8000,
    confirm_callback=None,
) -> str:
    """
    Dispatch a tool call by name and return the result as a string.
    """
    if tool_name == "read_file":
        return read_file(**tool_args)

    elif tool_name == "write_file":
        return write_file(**tool_args)

    elif tool_name == "patch_file":
        return patch_file(**tool_args)

    elif tool_name == "execute_bash":
        result = execute_bash(
            tool_args["command"],
            timeout=bash_timeout,
            max_output_chars=max_output_chars,
            confirm_callback=confirm_callback,
        )
        # Format the dict into a readable string for the LLM
        parts = []
        if result.get("error"):
            return f"ERROR: {result['error']}"
        if result["stdout"]:
            parts.append(f"STDOUT:\n{result['stdout']}")
        if result["stderr"]:
            parts.append(f"STDERR:\n{result['stderr']}")
        parts.append(f"Exit code: {result['exit_code']}")
        if result.get("truncated"):
            parts.append("(Output was truncated)")
        return "\n".join(parts) if parts else "(no output)"

    elif tool_name == "list_directory":
        return list_directory(
            path=tool_args.get("path", "."),
            max_depth=tool_args.get("max_depth", 2),
        )

    elif tool_name == "search_code":
        return search_code(
            pattern=tool_args["pattern"],
            path=tool_args.get("path", "."),
            file_pattern=tool_args.get("file_pattern"),
            case_sensitive=tool_args.get("case_sensitive", True),
        )

    else:
        return f"ERROR: Unknown tool: {tool_name}"
