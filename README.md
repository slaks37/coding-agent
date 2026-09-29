# 🤖 Coding Agent — Autonomous CLI Coding Assistant

An autonomous AI coding agent for the terminal. Supports **Anthropic Claude, OpenAI GPT, Google Gemini, OpenRouter, DeepSeek, Groq, and Ollama** via a single interface powered by [LiteLLM](https://github.com/BerriAI/litellm).

Inspired by Claude Code and Aider, but fully local, extensible, and provider-agnostic.

---

## ✨ Features

| Feature | Details |
|---|---|
| **Multi-provider** | Claude, GPT-4o, Gemini, DeepSeek, Groq, Ollama — switch with `/model` |
| **ReAct loop** | Reason → Act → Observe — autonomous tool-use until task complete |
| **6 built-in tools** | Read, write, patch files · bash runner · dir tree · code search |
| **Safety guardrails** | Dangerous commands (`rm -rf`, `DROP DATABASE`, etc.) require explicit `y/n` |
| **Context management** | Automatic history truncation before context window overflow |
| **Rich UI** | Syntax highlighting, spinners, panels, markdown rendering |
| **Configurable** | `.env` file or interactive first-run wizard; saved to `~/.coding_agent_config.json` |

---

## 📦 Installation

### 1. Clone & set up a virtual environment

```bash
git clone <repo-url>   # or copy the folder
cd coding_agent

python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your API key

**Option A** — Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
# Edit .env and add your key, e.g.:
# ANTHROPIC_API_KEY=sk-ant-...
```

**Option B** — Set an environment variable directly:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**Option C** — Run the agent and use the interactive setup wizard (no pre-config needed).

---

## 🚀 Usage

```bash
# Start the agent (uses current directory as workspace)
python main.py

# Start with a specific model
python main.py --model gpt-4o

# Set a specific workspace directory
python main.py --workspace /path/to/my/project

# Skip the startup banner
python main.py --no-banner
```

### Available slash commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/model` | Show current model |
| `/model gpt-4o` | Switch to GPT-4o |
| `/model gemini/gemini-2.5-flash` | Switch to Gemini |
| `/model ollama/llama3.3` | Switch to local Ollama |
| `/clear` | Reset conversation history |
| `/exit` or `/quit` | Exit the program |

---

## 💬 Example Session

```
You: List the project structure and find any TODO comments in the code

⚙ Tool: list_directory(path='.')
  Result: ...

⚙ Tool: search_code(pattern='TODO', path='.')
  Result: ...

Agent: I found 3 TODO comments across 2 files:
  - src/auth.py line 47: validate token expiry
  - src/db.py line 112: add retry logic
  ...

You: Fix the TODO in src/auth.py

⚙ Tool: read_file(path='src/auth.py', start_line=40, end_line=55)
⚙ Tool: patch_file(path='src/auth.py', target_string='# TODO: validate...', ...)
⚙ Tool: execute_bash(command='python -m pytest tests/test_auth.py -v')

Agent: Fixed! The token expiry validation has been implemented and tests pass. ✓
```

---

## 🔧 Supported Providers & Models

| Provider | Env Variable | Example Model |
|---|---|---|
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/gemini-2.5-flash` |
| OpenRouter | `OPENROUTER_API_KEY` | `openrouter/anthropic/claude-sonnet-4-5` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek/deepseek-chat` |
| Groq | `GROQ_API_KEY` | `groq/llama-3.3-70b-versatile` |
| Ollama (local) | *(none)* | `ollama/llama3.3` |

> **Tip:** LiteLLM supports 100+ providers. Any model string that LiteLLM accepts will work.

---

## 🛠 Tool Reference

### `read_file(path, start_line?, end_line?)`
Read a file with optional line range. Line numbers are prepended for easy reference.

### `write_file(path, content)`
Create or completely overwrite a file. Parent directories are created automatically.

### `patch_file(path, target_string, replacement_string)`
Surgical text replacement — only the **first** occurrence of `target_string` is replaced.
Faster and safer than rewriting the whole file.

### `execute_bash(command)`
Run any shell command. Output (stdout + stderr + exit code) is returned to the agent.
Commands matching dangerous patterns require user confirmation.

### `list_directory(path?, max_depth?)`
Render a directory tree (like `tree`). Skips `node_modules`, `.git`, `__pycache__` automatically.

### `search_code(pattern, path?, file_pattern?, case_sensitive?)`
Full-text / regex search across files (like `grep -rn`). Returns `file:line:content` matches.

---

## 🧪 Running Tests

```bash
# Install dev dependencies (already in requirements.txt)
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run only tool tests
pytest tests/test_tools.py -v

# Run only agent loop tests (uses mocks — no real API calls)
pytest tests/test_core.py -v

# Run with coverage
pytest tests/ --tb=short -q
```

---

## ⚙ Configuration File

Settings are saved to `~/.coding_agent_config.json`:

```json
{
  "model": "claude-sonnet-4-5",
  "api_key": "sk-ant-...",
  "provider": "anthropic",
  "max_tokens": 8192,
  "temperature": 0.2,
  "context_limit": 60000,
  "bash_timeout": 30,
  "max_output_chars": 8000,
  "max_retries": 3,
  "workspace": "/path/to/project"
}
```

You can edit this file directly to change defaults.

---

## 🔒 Safety

Dangerous commands are detected by regex patterns and require explicit `y/n` confirmation:

- `rm -rf` / `rm -fr`
- `git reset --hard` / `git clean -f`
- `DROP DATABASE` / `DROP TABLE` / `TRUNCATE TABLE`
- `DELETE FROM <table>` (without WHERE)
- `mkfs.*`, `dd of=`, `poweroff`, `shutdown`
- `chmod -R 777`
- `sudo rm`

---

## 📁 Project Structure

```
coding_agent/
├── agent/
│   ├── __init__.py      # Package metadata
│   ├── core.py          # ReAct agentic loop & LiteLLM orchestration
│   ├── tools.py         # Tool implementations (file I/O, bash, search)
│   ├── schemas.py       # JSON schemas for LLM function-calling
│   ├── config.py        # API key management & configuration
│   └── ui.py            # Rich display components & prompts
├── tests/
│   ├── test_tools.py    # Unit tests for all 6 tools
│   └── test_core.py     # Mock tests for the agent loop
├── .env.example         # API key template
├── requirements.txt     # Python dependencies
├── main.py              # CLI entry point
└── README.md            # This file
```

---

## 📄 License

MIT — use freely, modify as needed.
