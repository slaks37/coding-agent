"""
JSON Schema definitions for all tools exposed to the LLM via LiteLLM function-calling.
These schemas follow the OpenAI function-calling format, which LiteLLM normalises
for every supported provider.
"""

from __future__ import annotations

# ── Individual tool schemas ────────────────────────────────────────────────────

READ_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read the contents of a file on the local filesystem. "
            "Optionally restrict output to a line range to save tokens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-based start line (inclusive). Omit to start from line 1.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based end line (inclusive). Omit to read to end of file.",
                },
            },
            "required": ["path"],
        },
    },
}

WRITE_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": (
            "Create or completely overwrite a file with the given content. "
            "Parent directories are created automatically if they do not exist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write into the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
}

PATCH_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "patch_file",
        "description": (
            "Replace the FIRST occurrence of `target_string` inside a file with "
            "`replacement_string`. Fails if the target string is not found. "
            "Use this for surgical edits instead of rewriting the entire file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or absolute path to the file to patch.",
                },
                "target_string": {
                    "type": "string",
                    "description": "Exact substring to find (must be unique or first occurrence will be replaced).",
                },
                "replacement_string": {
                    "type": "string",
                    "description": "String to substitute in place of target_string.",
                },
            },
            "required": ["path", "target_string", "replacement_string"],
        },
    },
}

EXECUTE_BASH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "execute_bash",
        "description": (
            "Execute a shell command on the local system and return stdout, stderr, "
            "and the exit code. Output is truncated if it exceeds the limit. "
            "Avoid commands that require interactive input. "
            "DANGEROUS commands (rm -rf, git reset --hard, drop database, etc.) "
            "will prompt the user for confirmation before execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
            },
            "required": ["command"],
        },
    },
}

LIST_DIRECTORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": (
            "List the directory tree rooted at `path` up to `max_depth` levels deep. "
            "Returns a formatted tree string. Hidden files/dirs (starting with '.') "
            "are included by default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Root directory to list. Defaults to current directory '.'.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum depth to traverse. Defaults to 2.",
                },
            },
            "required": [],
        },
    },
}

SEARCH_CODE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_code",
        "description": (
            "Search for a text pattern (plain text or Python regex) across all files "
            "under `path`. Returns matching lines with file paths and line numbers. "
            "Binary files are skipped. Use this to locate function definitions, "
            "usages, TODO comments, error messages, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file path to search within. Defaults to '.'.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern to filter files, e.g. '*.py' or '*.ts'. "
                        "Defaults to all files."
                    ),
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether the search is case-sensitive. Defaults to True.",
                },
            },
            "required": ["pattern"],
        },
    },
}

# ── Master list of all tool schemas ───────────────────────────────────────────

ALL_TOOLS: list[dict] = [
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    PATCH_FILE_SCHEMA,
    EXECUTE_BASH_SCHEMA,
    LIST_DIRECTORY_SCHEMA,
    SEARCH_CODE_SCHEMA,
]

# Mapping tool name → schema for quick lookup
TOOL_MAP: dict[str, dict] = {t["function"]["name"]: t for t in ALL_TOOLS}
