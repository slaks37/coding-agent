"""
Configuration management: API keys, model settings, and environment variables.
Supports loading from .env files, environment variables, and a local JSON config file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env from current working directory (if present)
load_dotenv(override=False)

CONFIG_FILE = Path.home() / ".coding_agent_config.json"

# ── Provider → (env_var, default_model) ──────────────────────────────────────
PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-5",
        "prefix": "claude-",
    },
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "prefix": "gpt-",
    },
    "gemini": {
        "env_var": "GEMINI_API_KEY",
        "default_model": "gemini/gemini-2.5-flash",
        "prefix": "gemini/",
    },
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "default_model": "openrouter/anthropic/claude-sonnet-4-5",
        "prefix": "openrouter/",
    },
    "deepseek": {
        "env_var": "DEEPSEEK_API_KEY",
        "default_model": "deepseek/deepseek-chat",
        "prefix": "deepseek/",
    },
    "groq": {
        "env_var": "GROQ_API_KEY",
        "default_model": "groq/llama-3.3-70b-versatile",
        "prefix": "groq/",
    },
    "ollama": {
        "env_var": "",
        "default_model": "ollama/llama3.3",
        "prefix": "ollama/",
    },
}

ENV_VARS = [info["env_var"] for info in PROVIDERS.values() if info["env_var"]]


class AgentConfig(BaseModel):
    """Validated agent configuration."""

    model: str = Field(default="claude-sonnet-4-5", description="Active LiteLLM model string")
    api_key: Optional[str] = Field(default=None, description="API key for the selected provider")
    provider: str = Field(default="anthropic", description="Provider name")
    max_tokens: int = Field(default=8192, description="Max tokens per response")
    temperature: float = Field(default=0.2, description="LLM temperature")
    context_limit: int = Field(default=60000, description="Approx token limit before truncation")
    bash_timeout: int = Field(default=30, description="Timeout (seconds) for bash commands")
    max_output_chars: int = Field(default=8000, description="Max chars captured from bash output")
    max_retries: int = Field(default=3, description="Max agentic loop iterations per request")
    workspace: str = Field(default=".", description="Working directory for the agent")

    model_config = {"extra": "allow"}


def _detect_provider_from_env() -> tuple[str, str, str] | None:
    """
    Scan environment variables and return (provider, api_key, default_model)
    for the first provider whose key is set and non-empty.
    """
    for provider, info in PROVIDERS.items():
        env_var = info["env_var"]
        if env_var and (key := os.environ.get(env_var, "").strip()):
            return provider, key, info["default_model"]
    return None


def load_config() -> AgentConfig:
    """
    Load agent configuration with priority:
      1. Saved JSON config file (~/.coding_agent_config.json)
      2. Environment variables / .env file
    Returns an AgentConfig (may have api_key=None if nothing found yet).
    """
    # --- Try saved config first ---
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            cfg = AgentConfig(**data)
            # Re-inject key from env if config file doesn't have it stored
            if not cfg.api_key:
                detected = _detect_provider_from_env()
                if detected:
                    _, key, _ = detected
                    cfg.api_key = key
            return cfg
        except Exception:
            pass  # Fall through to env detection

    # --- Try environment variables ---
    detected = _detect_provider_from_env()
    if detected:
        provider, key, model = detected
        return AgentConfig(provider=provider, api_key=key, model=model)

    # --- Return blank config (interactive setup will populate it) ---
    return AgentConfig()


def save_config(cfg: AgentConfig) -> None:
    """Persist the config to ~/.coding_agent_config.json."""
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2))


def set_env_for_litellm(cfg: AgentConfig) -> None:
    """
    Inject the API key into the correct environment variable so that
    LiteLLM can pick it up automatically.
    """
    if not cfg.api_key:
        return
    provider_info = PROVIDERS.get(cfg.provider, {})
    env_var = provider_info.get("env_var", "")
    if env_var:
        os.environ[env_var] = cfg.api_key
