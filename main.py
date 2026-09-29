#!/usr/bin/env python3
"""
main.py — Entry point for the Autonomous CLI Coding Agent.

Usage:
    python main.py [--model MODEL] [--workspace DIR]

Slash commands (at the prompt):
    /help       Show available commands
    /model      View or switch model (/model gpt-4o)
    /clear      Reset conversation history
    /exit       Quit
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.prompt import Prompt

# Ensure the package root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from agent.config import (
    PROVIDERS,
    AgentConfig,
    load_config,
    save_config,
    set_env_for_litellm,
)
from agent.core import CodingAgent
from agent.ui import (
    console,
    print_banner,
    print_error,
    print_help,
    print_info,
    print_model_info,
    print_success,
    print_warning,
    prompt_api_key_setup,
    prompt_user_input,
)


# ── CLI entry ──────────────────────────────────────────────────────────────────

@click.command()
@click.option("--model", "-m", default=None, help="Override the active LLM model.")
@click.option(
    "--workspace", "-w",
    default=".",
    show_default=True,
    help="Set the working directory for the agent.",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.option("--no-banner", is_flag=True, default=False, help="Skip the startup banner.")
def main(model: str | None, workspace: str, no_banner: bool) -> None:
    """Autonomous CLI Coding Agent — AI-powered terminal assistant."""

    # ── Change working directory ───────────────────────────────────────────────
    workspace_path = Path(workspace).resolve()
    os.chdir(workspace_path)

    # ── Load configuration ────────────────────────────────────────────────────
    cfg = load_config()
    cfg.workspace = str(workspace_path)

    # Override model from CLI flag
    if model:
        cfg.model = model

    # ── First-time setup ──────────────────────────────────────────────────────
    if not cfg.api_key and cfg.provider != "ollama":
        provider, chosen_model, api_key = prompt_api_key_setup()
        cfg.provider = provider
        cfg.model = chosen_model
        cfg.api_key = api_key
        save_config(cfg)
        print_success("Configuration saved to ~/.coding_agent_config.json")

    # Inject API key into environment so LiteLLM picks it up
    set_env_for_litellm(cfg)

    # ── Display banner ────────────────────────────────────────────────────────
    if not no_banner:
        print_banner(model=cfg.model, provider=cfg.provider, workspace=str(workspace_path))

    # ── Instantiate agent ─────────────────────────────────────────────────────
    agent = CodingAgent(cfg)

    # ── REPL loop ─────────────────────────────────────────────────────────────
    while True:
        try:
            user_input = prompt_user_input()
        except (KeyboardInterrupt, EOFError):
            print_info("\nInterrupted. Type /exit to quit.")
            continue

        user_input = user_input.strip()
        if not user_input:
            continue

        # ── Slash command handler ─────────────────────────────────────────────
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if command in ("/exit", "/quit"):
                print_info("Goodbye! 👋")
                sys.exit(0)

            elif command == "/help":
                print_help()

            elif command == "/clear":
                agent.clear_history()

            elif command == "/model":
                if not arg:
                    print_model_info(cfg.model, cfg.provider)
                    print_info("Usage: /model <model-name>  (e.g. /model gpt-4o)")
                else:
                    # Detect provider from model prefix
                    new_model = arg
                    new_provider = cfg.provider  # keep current unless prefix matches
                    for pname, pinfo in PROVIDERS.items():
                        prefix = pinfo.get("prefix", "")
                        if prefix and new_model.startswith(prefix):
                            new_provider = pname
                            break
                    cfg.model = new_model
                    cfg.provider = new_provider
                    save_config(cfg)
                    set_env_for_litellm(cfg)
                    agent.config = cfg
                    print_model_info(new_model, new_provider)

            else:
                print_warning(f"Unknown command: {command}. Type /help for a list of commands.")

            continue

        # ── Regular agent invocation ──────────────────────────────────────────
        try:
            agent.run(user_input)
        except KeyboardInterrupt:
            print_warning("\nStopped. (Press Ctrl+C again or type /exit to quit.)")
        except Exception as exc:
            print_error(f"Unexpected error: {type(exc).__name__}: {exc}")
            console.print_exception(show_locals=False)


if __name__ == "__main__":
    main()
