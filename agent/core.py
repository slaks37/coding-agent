"""
Core agentic loop: orchestrates LiteLLM calls, tool dispatching, context management,
and the ReAct (Reason + Act) cycle.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import litellm
from litellm import completion

from .config import AgentConfig, save_config, set_env_for_litellm
from .schemas import ALL_TOOLS
from .tools import dispatch_tool
from .ui import (
    ThinkingSpinner,
    console,
    print_agent_response,
    print_error,
    print_info,
    print_success,
    print_tool_call,
    print_tool_result,
    print_warning,
    prompt_danger_confirm,
)

# Silence LiteLLM verbose logging
litellm.suppress_debug_info = True
litellm.set_verbose = False

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an autonomous CLI coding agent running on the user's local machine.

Your job is to help the user write, modify, debug, and understand code. You operate in a
ReAct (Reason + Act) loop: think about what needs to be done, use tools to do it, observe
the results, and continue until the task is complete.

## Rules
1. **Always read before editing**: Use `read_file` or `search_code` before modifying files you haven't seen.
2. **Prefer surgical patches**: Use `patch_file` for small targeted changes; `write_file` only for new files or complete rewrites.
3. **Verify with bash**: After modifying code, run tests or linters with `execute_bash` to confirm correctness.
4. **Error recovery**: If a command fails, analyse the error output, identify the root cause, fix it, and retry.
5. **Explain actions**: Before using each tool, briefly explain *why* you're using it.
6. **Be concise**: Don't repeat the user's question. Get to work.
7. **Safety**: Never guess at destructive actions. If unsure, ask before proceeding.
8. **Context**: The user's working directory is the project root. Use relative paths when possible.

## Tool capabilities
- `read_file(path, start_line, end_line)` — read file contents
- `write_file(path, content)` — create or overwrite a file
- `patch_file(path, target_string, replacement_string)` — surgical text replacement
- `execute_bash(command)` — run shell commands, tests, installs
- `list_directory(path, max_depth)` — inspect project structure
- `search_code(pattern, path, file_pattern, case_sensitive)` — grep across files

Start by understanding the project structure if given an open-ended task.
"""


# ── Message helpers ───────────────────────────────────────────────────────────

def _estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: ~4 chars per token."""
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    return total_chars // 4


def _truncate_history(
    messages: list[dict],
    context_limit: int,
    keep_system: bool = True,
) -> list[dict]:
    """
    Remove oldest user/assistant messages when the history is too large.
    Always keeps the system message and the most recent exchange.
    """
    while _estimate_tokens(messages) > context_limit and len(messages) > 2:
        # Find the first non-system message and remove it
        for i, msg in enumerate(messages):
            if msg.get("role") != "system":
                messages.pop(i)
                # Also remove the paired message if it was a tool result
                break
        else:
            break

    return messages


def _format_tool_result_message(tool_call_id: str, name: str, result: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": result,
    }


# ── Agent class ───────────────────────────────────────────────────────────────

class CodingAgent:
    """
    The main autonomous coding agent.

    Maintains conversation history and runs the ReAct loop:
      User Input → LLM Planning → Tool Call → Tool Execution → Result → Next Action
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.history: list[dict] = []
        self._reset_history()
        set_env_for_litellm(config)

    # ── Public API ────────────────────────────────────────────────────────────

    def clear_history(self) -> None:
        """Reset conversation history (keeps system prompt)."""
        self._reset_history()
        print_success("Conversation history cleared.")

    def set_model(self, model: str) -> None:
        """Switch to a different model."""
        self.config.model = model
        save_config(self.config)
        print_success(f"Switched to model: [bold]{model}[/bold]")

    def run(self, user_input: str) -> None:
        """
        Process a user message through the full ReAct loop.
        Handles multi-step tool calls until the agent signals completion.
        """
        # Add user message
        self.history.append({"role": "user", "content": user_input})

        iteration = 0
        max_iter = self.config.max_retries * 5  # Allow enough iterations for complex tasks

        while iteration < max_iter:
            iteration += 1

            # Truncate if needed
            self.history = _truncate_history(self.history, self.config.context_limit)

            # Call LLM
            response_message = self._call_llm()
            if response_message is None:
                return

            # Add assistant message to history
            self.history.append(response_message)

            tool_calls = response_message.get("tool_calls") or []

            # No tool calls → final answer
            if not tool_calls:
                content = response_message.get("content") or ""
                if content:
                    print_agent_response(content)
                return

            # ── Execute all tool calls in the response ────────────────────────
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError) as exc:
                    tool_args = {}
                    print_warning(f"Could not parse tool arguments: {exc}")

                print_tool_call(tool_name, tool_args)

                # Execute the tool
                result = dispatch_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    bash_timeout=self.config.bash_timeout,
                    max_output_chars=self.config.max_output_chars,
                    confirm_callback=self._confirm_dangerous_command,
                )

                print_tool_result(result, tool_name)

                # Add tool result to history
                self.history.append(
                    _format_tool_result_message(tc["id"], tool_name, result)
                )

            # Show any text content alongside tool calls
            content = response_message.get("content") or ""
            if content and content.strip():
                print_agent_response(content)

        print_warning(f"Reached maximum iterations ({max_iter}). Stopping.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _reset_history(self) -> None:
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _confirm_dangerous_command(self, command: str) -> bool:
        """Callback passed to execute_bash for dangerous command confirmation."""
        return prompt_danger_confirm(command)

    def _call_llm(self) -> Optional[dict]:
        """
        Call LiteLLM with current history and return the assistant message dict.
        Shows a spinner while waiting.
        """
        with ThinkingSpinner("Agent is thinking…"):
            try:
                response = completion(
                    model=self.config.model,
                    messages=self.history,
                    tools=ALL_TOOLS,
                    tool_choice="auto",
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
            except litellm.exceptions.AuthenticationError as exc:
                print_error(f"Authentication failed: {exc}\nCheck your API key with /model or update ~/.coding_agent_config.json")
                return None
            except litellm.exceptions.RateLimitError as exc:
                print_error(f"Rate limit exceeded: {exc}")
                return None
            except litellm.exceptions.ContextWindowExceededError:
                print_warning("Context window exceeded — truncating history and retrying.")
                # Force aggressive truncation
                self.history = self.history[:1] + self.history[-4:]
                return self._call_llm()
            except litellm.exceptions.BadRequestError as exc:
                print_error(f"Bad request: {exc}")
                return None
            except Exception as exc:
                print_error(f"LLM call failed: {type(exc).__name__}: {exc}")
                return None

        choice = response.choices[0]
        msg = choice.message

        # Normalise to a plain dict for storage
        result: dict = {"role": "assistant"}

        if hasattr(msg, "content") and msg.content:
            result["content"] = msg.content
        else:
            result["content"] = ""

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        return result
