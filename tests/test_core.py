"""
Mock tests for agent/core.py — tests the agentic loop without real LLM calls.
Run with: pytest tests/test_core.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.config import AgentConfig
from agent.core import CodingAgent, _estimate_tokens, _truncate_history


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_config(**kwargs) -> AgentConfig:
    defaults = dict(
        model="claude-sonnet-4-5",
        api_key="test-key",
        provider="anthropic",
        max_tokens=1024,
        temperature=0.2,
        context_limit=4000,
        bash_timeout=5,
        max_output_chars=500,
        max_retries=2,
    )
    defaults.update(kwargs)
    return AgentConfig(**defaults)


def make_llm_response(content: str = "", tool_calls: list | None = None) -> dict:
    """Build a mock assistant message dict."""
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def make_tool_call(name: str, args: dict, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def make_mock_completion(content: str = "", tool_calls: list | None = None) -> MagicMock:
    """Return a mocked litellm.completion response."""
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = []

    if tool_calls:
        tc_list = []
        for tc in tool_calls:
            mock_tc = MagicMock()
            mock_tc.id = tc["id"]
            mock_tc.function = MagicMock()
            mock_tc.function.name = tc["function"]["name"]
            mock_tc.function.arguments = tc["function"]["arguments"]
            tc_list.append(mock_tc)
        mock_message.tool_calls = tc_list

    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_message
    return mock_response


# ── Token estimation ──────────────────────────────────────────────────────────

class TestEstimateTokens:
    def test_empty_messages(self) -> None:
        assert _estimate_tokens([]) == 0

    def test_simple_messages(self) -> None:
        msgs = [{"role": "user", "content": "hello world"}]
        est = _estimate_tokens(msgs)
        assert est > 0
        assert est < 10  # "hello world" is ~3 tokens

    def test_grows_with_content(self) -> None:
        short = [{"role": "user", "content": "hi"}]
        long = [{"role": "user", "content": "x" * 1000}]
        assert _estimate_tokens(long) > _estimate_tokens(short)


# ── Context truncation ────────────────────────────────────────────────────────

class TestTruncateHistory:
    def test_short_history_unchanged(self) -> None:
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = _truncate_history(list(msgs), context_limit=10000)
        assert len(result) == 3

    def test_truncates_when_over_limit(self) -> None:
        msgs = [
            {"role": "system", "content": "sys"},
        ]
        # Add many large messages — each pair is ~250 tokens
        for i in range(20):
            msgs.append({"role": "user", "content": "x" * 500})
            msgs.append({"role": "assistant", "content": "y" * 500})

        original_count = len(msgs)
        # Use a very low limit to force truncation
        result = _truncate_history(msgs, context_limit=10)
        # At minimum, some messages must have been removed
        assert len(result) < original_count

    def test_system_message_preserved(self) -> None:
        msgs = [
            {"role": "system", "content": "SYSTEM_MUST_STAY"},
            {"role": "user", "content": "x" * 2000},
            {"role": "assistant", "content": "y" * 2000},
        ]
        result = _truncate_history(msgs, context_limit=100)
        assert any(m["content"] == "SYSTEM_MUST_STAY" for m in result)


# ── CodingAgent ───────────────────────────────────────────────────────────────

class TestCodingAgent:
    @pytest.fixture
    def agent(self) -> CodingAgent:
        with patch("agent.core.set_env_for_litellm"):
            return CodingAgent(make_config())

    def test_initial_history_has_system_message(self, agent: CodingAgent) -> None:
        assert len(agent.history) == 1
        assert agent.history[0]["role"] == "system"

    def test_clear_history_resets(self, agent: CodingAgent) -> None:
        agent.history.append({"role": "user", "content": "test"})
        agent.clear_history()
        assert len(agent.history) == 1
        assert agent.history[0]["role"] == "system"

    def test_set_model_updates_config(self, agent: CodingAgent, tmp_path: Path) -> None:
        with patch("agent.core.save_config") as mock_save:
            agent.set_model("gpt-4o")
            assert agent.config.model == "gpt-4o"
            mock_save.assert_called_once()

    @patch("agent.core.completion")
    def test_run_plain_response(self, mock_completion: MagicMock, agent: CodingAgent) -> None:
        """Agent returns a plain text response with no tool calls."""
        mock_completion.return_value = make_mock_completion(content="Hello from agent!")

        with patch("agent.core.print_agent_response") as mock_print:
            agent.run("Say hello")
            mock_print.assert_called_once_with("Hello from agent!")

        # History should have: system, user, assistant
        assert len(agent.history) == 3
        assert agent.history[1]["role"] == "user"
        assert agent.history[2]["role"] == "assistant"

    @patch("agent.core.completion")
    def test_run_with_tool_call_then_final_response(
        self, mock_completion: MagicMock, agent: CodingAgent, tmp_path: Path
    ) -> None:
        """Agent first calls a tool, then gives a final response."""
        # Create a real temp file so read_file works
        test_file = tmp_path / "hello.txt"
        test_file.write_text("hello world")

        tool_call = make_tool_call("read_file", {"path": str(test_file)})

        # First LLM call returns a tool_call; second returns final text
        mock_completion.side_effect = [
            make_mock_completion(tool_calls=[tool_call]),
            make_mock_completion(content="I read the file. It says: hello world."),
        ]

        with patch("agent.core.print_agent_response") as mock_print:
            with patch("agent.core.print_tool_call"):
                with patch("agent.core.print_tool_result"):
                    agent.run("Read the hello file")
                    mock_print.assert_called_once()

        # History: system, user, assistant (tool call), tool result, assistant (final)
        roles = [m["role"] for m in agent.history]
        assert "tool" in roles

    @patch("agent.core.completion")
    def test_run_patches_file_via_tool(
        self, mock_completion: MagicMock, agent: CodingAgent, tmp_path: Path
    ) -> None:
        """Agent uses patch_file tool to fix code."""
        test_file = tmp_path / "code.py"
        test_file.write_text("def broken():\n    return None\n")

        tool_call = make_tool_call(
            "patch_file",
            {
                "path": str(test_file),
                "target_string": "return None",
                "replacement_string": "return 42",
            },
        )

        mock_completion.side_effect = [
            make_mock_completion(tool_calls=[tool_call]),
            make_mock_completion(content="Fixed! The function now returns 42."),
        ]

        with patch("agent.core.print_agent_response"):
            with patch("agent.core.print_tool_call"):
                with patch("agent.core.print_tool_result"):
                    agent.run("Fix the broken function to return 42")

        # Verify the file was actually patched
        assert "return 42" in test_file.read_text()

    @patch("agent.core.completion")
    def test_authentication_error_handled(
        self, mock_completion: MagicMock, agent: CodingAgent
    ) -> None:
        """AuthenticationError should be caught and print an error message."""
        import litellm

        mock_completion.side_effect = litellm.exceptions.AuthenticationError(
            message="Invalid key", llm_provider="anthropic", model="claude-sonnet-4-5"
        )

        with patch("agent.core.print_error") as mock_error:
            agent.run("Hello")
            mock_error.assert_called_once()
            assert "Authentication" in mock_error.call_args[0][0]

    @patch("agent.core.completion")
    def test_context_window_exceeded_triggers_truncation(
        self, mock_completion: MagicMock, agent: CodingAgent
    ) -> None:
        """ContextWindowExceededError should trigger truncation and retry."""
        import litellm

        # First call: context exceeded; second call: success
        mock_completion.side_effect = [
            litellm.exceptions.ContextWindowExceededError(
                message="Too many tokens",
                model="claude-sonnet-4-5",
                llm_provider="anthropic",
            ),
            make_mock_completion(content="After truncation."),
        ]

        # Add some history so truncation has something to remove
        for i in range(10):
            agent.history.append({"role": "user", "content": f"Message {i}: " + "x" * 100})
            agent.history.append({"role": "assistant", "content": "Response " + "y" * 100})

        with patch("agent.core.print_agent_response"):
            with patch("agent.core.print_warning"):
                agent.run("Trigger context overflow")

        # completion was called twice
        assert mock_completion.call_count == 2

    @patch("agent.core.completion")
    def test_dangerous_command_denied_by_agent(
        self, mock_completion: MagicMock, agent: CodingAgent, tmp_path: Path
    ) -> None:
        """Dangerous commands are routed through confirm_callback."""
        tool_call = make_tool_call("execute_bash", {"command": "rm -rf /tmp/test_dir"})

        mock_completion.side_effect = [
            make_mock_completion(tool_calls=[tool_call]),
            make_mock_completion(content="Command was denied."),
        ]

        # Override confirm_callback to always deny
        agent._confirm_dangerous_command = lambda cmd: False

        with patch("agent.core.print_agent_response"):
            with patch("agent.core.print_tool_call"):
                with patch("agent.core.print_tool_result") as mock_result:
                    agent.run("Delete everything")
                    # The tool result should mention aborted
                    call_args = mock_result.call_args[0][0]
                    assert "aborted" in call_args.lower() or "error" in call_args.lower()

    @patch("agent.core.completion")
    def test_max_iterations_stop(
        self, mock_completion: MagicMock, agent: CodingAgent
    ) -> None:
        """Agent must stop after max iterations even without a final response."""
        # Always return a tool call — never a final response
        tool_call = make_tool_call("execute_bash", {"command": "echo loop"})
        mock_completion.return_value = make_mock_completion(tool_calls=[tool_call])

        agent.config.max_retries = 1  # max_iter = max_retries * 5 = 5

        with patch("agent.core.print_tool_call"):
            with patch("agent.core.print_tool_result"):
                with patch("agent.core.print_warning") as mock_warn:
                    agent.run("Loop forever")
                    # Should have warned about reaching max iterations
                    mock_warn.assert_called()
