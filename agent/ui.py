"""
Rich-based UI components: banner, panels, spinners, prompts, and formatting helpers.
"""

from __future__ import annotations

import sys
from typing import Optional

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ── Console setup ─────────────────────────────────────────────────────────────

THEME = Theme(
    {
        "agent": "bold cyan",
        "user": "bold green",
        "tool": "bold yellow",
        "tool_result": "dim white",
        "error": "bold red",
        "success": "bold green",
        "info": "dim cyan",
        "warning": "bold yellow",
        "separator": "dim white",
    }
)

console = Console(theme=THEME, highlight=True)

# ── Banner ────────────────────────────────────────────────────────────────────

BANNER_ART = r"""
   _____          _ _               ___                    _
  / ____|        | (_)             / _ \                  | |
 | |     ___   __| |_ _ __   __ _| |_| | __ _  ___ _ __ | |_
 | |    / _ \ / _` | | '_ \ / _` |  _  |/ _` |/ _ \ '_ \| __|
 | |___| (_) | (_| | | | | | (_| | | | | (_| |  __/ | | | |_
  \_____\___/ \__,_|_|_| |_|\__, |_| |_|\__, |\___|_| |_|\__|
                              __/ |       __/ |
                             |___/       |___/
"""


def print_banner(model: str, provider: str, workspace: str) -> None:
    """Print the startup banner with current configuration."""
    art = Text(BANNER_ART, style="bold cyan", justify="center")
    subtitle = Text("Autonomous CLI Coding Agent  •  v1.0.0", style="dim white", justify="center")

    info_table = Table.grid(padding=(0, 2))
    info_table.add_column(style="dim white")
    info_table.add_column(style="bold white")
    info_table.add_row("🤖  Model", model)
    info_table.add_row("🔌  Provider", provider)
    info_table.add_row("📁  Workspace", workspace)
    info_table.add_row("💡  Help", "Type /help for available commands")

    inner = Align.center(
        Columns(
            [
                Align.center(subtitle),
            ]
        )
    )

    console.print(art)
    console.print(Align.center(subtitle))
    console.print()
    console.print(Panel(Align.center(info_table), border_style="cyan", box=box.ROUNDED))
    console.print()


# ── Help table ────────────────────────────────────────────────────────────────

HELP_COMMANDS = [
    ("/help", "Show this help message"),
    ("/model [name]", "View or change the active model (e.g. /model gpt-4o)"),
    ("/clear", "Reset the conversation history"),
    ("/exit  or  /quit", "Exit the program"),
]

AVAILABLE_TOOLS = [
    ("read_file", "Read a file (with optional line range)"),
    ("write_file", "Create or overwrite a file"),
    ("patch_file", "Surgically replace a substring in a file"),
    ("execute_bash", "Run shell commands (with safety guardrails)"),
    ("list_directory", "Map project directory tree"),
    ("search_code", "Search text/regex across files"),
]


def print_help() -> None:
    """Render the help panel."""
    cmd_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
    cmd_table.add_column("Command", style="yellow")
    cmd_table.add_column("Description")
    for cmd, desc in HELP_COMMANDS:
        cmd_table.add_row(cmd, desc)

    tool_table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
    tool_table.add_column("Tool", style="yellow")
    tool_table.add_column("Description")
    for tool, desc in AVAILABLE_TOOLS:
        tool_table.add_row(tool, desc)

    console.print(Panel(cmd_table, title="[bold]Slash Commands[/bold]", border_style="cyan"))
    console.print(Panel(tool_table, title="[bold]Available Agent Tools[/bold]", border_style="cyan"))


# ── Message display ───────────────────────────────────────────────────────────

def print_user_message(text: str) -> None:
    console.print(Rule(style="separator"))
    console.print(Panel(text, title="[user]You[/user]", border_style="green", box=box.SIMPLE_HEAD))


def print_agent_response(text: str) -> None:
    """Render the agent's markdown response."""
    try:
        md = Markdown(text)
    except Exception:
        md = text  # type: ignore[assignment]
    console.print(Panel(md, title="[agent]Agent[/agent]", border_style="cyan", box=box.SIMPLE_HEAD))


def print_tool_call(tool_name: str, tool_args: dict) -> None:
    """Render a tool invocation notice."""
    args_text = "  ".join(f"{k}={repr(v)[:80]}" for k, v in tool_args.items())
    console.print(
        f"  [tool]⚙ Tool:[/tool] [bold]{tool_name}[/bold]([dim]{args_text}[/dim])"
    )


def print_tool_result(result: str, tool_name: str = "") -> None:
    """Render the result returned by a tool."""
    if len(result) > 2000:
        preview = result[:2000] + f"\n... [{len(result) - 2000} chars truncated]"
    else:
        preview = result

    # Use syntax highlighting for known language outputs
    lang_map = {
        "read_file": "text",
        "write_file": "text",
        "patch_file": "text",
        "execute_bash": "bash",
        "list_directory": "text",
        "search_code": "text",
    }
    lang = lang_map.get(tool_name, "text")

    if lang == "bash" and ("\n" in preview):
        syntax = Syntax(preview, "bash", theme="monokai", line_numbers=False, word_wrap=True)
        console.print(Panel(syntax, title=f"[tool_result]Result: {tool_name}[/tool_result]", border_style="dim yellow", box=box.SIMPLE))
    else:
        console.print(
            Panel(
                Text(preview, style="tool_result"),
                title=f"[tool_result]Result: {tool_name}[/tool_result]",
                border_style="dim yellow",
                box=box.SIMPLE,
            )
        )


def print_error(message: str) -> None:
    console.print(f"[error]✗ Error:[/error] {message}")


def print_info(message: str) -> None:
    console.print(f"[info]ℹ  {message}[/info]")


def print_success(message: str) -> None:
    console.print(f"[success]✓ {message}[/success]")


def print_warning(message: str) -> None:
    console.print(f"[warning]⚠  {message}[/warning]")


# ── Spinner context manager ───────────────────────────────────────────────────

class ThinkingSpinner:
    """Context manager that shows a spinner while the agent is processing."""

    def __init__(self, message: str = "Agent is thinking…"):
        self._message = message
        self._live = None

    def __enter__(self):
        from rich.live import Live

        spinner = Spinner("dots", text=Text(f" {self._message}", style="dim cyan"))
        self._live = Live(spinner, console=console, refresh_per_second=10, transient=True)
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.__exit__(*args)


# ── Interactive prompts ───────────────────────────────────────────────────────

def prompt_user_input(prompt_text: str = "") -> str:
    """Read a line of input from the user using Rich's Prompt."""
    try:
        return Prompt.ask(f"\n[user]You[/user]", console=console, default="")
    except (EOFError, KeyboardInterrupt):
        return "/exit"


def prompt_api_key_setup() -> tuple[str, str, str]:
    """
    Interactive setup wizard: ask for provider, model, and API key.
    Returns (provider, model, api_key).
    """
    from .config import PROVIDERS

    console.print(
        Panel(
            "[bold yellow]First-time Setup[/bold yellow]\n\n"
            "No API key was detected. Please configure your LLM provider.\n"
            "Your key will be saved to [bold]~/.coding_agent_config.json[/bold].",
            border_style="yellow",
        )
    )

    provider_list = list(PROVIDERS.keys())
    console.print("\n[bold]Available providers:[/bold]")
    for i, p in enumerate(provider_list, 1):
        console.print(f"  [yellow]{i}.[/yellow] {p}  (default: {PROVIDERS[p]['default_model']})")

    while True:
        choice = Prompt.ask("\nSelect provider number or name", default="1", console=console)
        if choice.isdigit() and 1 <= int(choice) <= len(provider_list):
            provider = provider_list[int(choice) - 1]
            break
        elif choice in PROVIDERS:
            provider = choice
            break
        console.print("[error]Invalid choice, try again.[/error]")

    default_model = PROVIDERS[provider]["default_model"]
    model = Prompt.ask(
        f"Enter model name",
        default=default_model,
        console=console,
    )

    api_key = ""
    if PROVIDERS[provider]["env_var"]:  # ollama doesn't need a key
        api_key = Prompt.ask(
            f"Enter your {provider.upper()} API key",
            password=True,
            console=console,
        )

    return provider, model, api_key


def prompt_danger_confirm(command: str) -> bool:
    """Ask the user to confirm a potentially dangerous command."""
    console.print(
        Panel(
            f"[bold red]⚠  DANGEROUS COMMAND DETECTED[/bold red]\n\n"
            f"[bold]{command}[/bold]\n\n"
            "This command may cause irreversible changes to your system.",
            border_style="red",
            box=box.HEAVY,
        )
    )
    return Confirm.ask("[bold red]Proceed anyway?[/bold red]", default=False, console=console)


def print_model_info(model: str, provider: str) -> None:
    console.print(f"[info]Active model:[/info] [bold]{model}[/bold]  (provider: {provider})")
