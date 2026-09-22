# OpenAI Agents API TUI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Watch the demo](https://img.youtube.com/vi/eaw8XBdm4RI/maxresdefault.jpg)](https://youtu.be/eaw8XBdm4RI)

A terminal user interface built with [Textual](https://textual.textualize.io/) for interacting with the **OpenAI Agents API**. Supports creating and managing sessions, sending messages, streaming agent responses, and launching the CODEX harness as a subprocess for `openai_hosted` environments.

> 🤖 **Built with [IBM Bob](https://www.ibm.com/products/bob)**

---

## Scope

The TUI wraps the OpenAI `beta.agents` API surface and provides:

| Feature | Description |
|---|---|
| **Session management** | Create, connect to, list, and delete agent sessions via the API |
| **Turns** | Send messages and stream agent responses in real time |
| **Environment types** | Supports `none`, `self_hosted` (local workspace), and `openai_hosted` (remote OpenAI sandbox) |
| **CODEX Harness** | Automatically launches `codex exec-server` as a child process for `openai_hosted` sessions |
| **Tool calls** | Dispatches function tool calls (e.g. CEP/customer lookup) and feeds results back to the agent |
| **Verbose mode** | Toggle between showing only agent output and showing all raw event stream events |
| **Input history** | Navigable command/message history persisted across sessions (↑ / ↓) |
| **Autocomplete** | Tab-completion for slash commands |

---

## Requirements

- Python 3.12+
- Node.js with `@openai/codex` installed globally (required only for `openai_hosted` environment)
- An `OPENAI_API_KEY` set in your environment or in a `.env` file

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Running

```bash
python -m tui
```

---

## Commands

All commands start with `/`. Any text without a leading `/` is sent as a message to the active agent.

### Configuration

| Command | Description |
|---|---|
| `/set-environment <none\|self\|openai>` | Set the environment type for the next session |
| `/set-model <model>` | Set the agent model (default: `gpt-6-astra`) |
| `/set-instructions <text>` | Set the system instructions for the agent |

### Session lifecycle

| Command | Description |
|---|---|
| `/create-session [--web_search] [--tool_cep] [<initial message>]` | Create a new session. `--web_search` enables web search with low reasoning effort; `--tool_cep` registers the CEP/customer lookup function tool. Optionally send an initial message immediately. |
| `/connect-session <session_id>` | Attach to an existing session by ID |
| `/delete-session` | Delete the active session (and stop its CODEX harness if running) |
| `/delete-other-sessions` | Delete all API sessions except the currently active one |
| `/list-sessions [<limit>]` | List active sessions from the API (default: 20) |

### Session inspection

| Command | Description |
|---|---|
| `/session-stats` | Show token usage summary for the active session (turns, input/output/cached/reasoning tokens) |
| `/session-inspect` | Print all session attributes as copy-pasteable Python |

### CODEX Harness

| Command | Description |
|---|---|
| `/harness-script` | Print the `codex exec-server` shell command for the active session's environment |
| `/list-codex` | List running `codex exec-server` processes managed by the TUI |

### General

| Command | Description |
|---|---|
| `/verbose` | Toggle verbose event display (show all raw Event Stream events) |
| `/help` | Show the help message inside the TUI |
| `/exit` | Delete the active session, stop all processes, and quit |

---

## Key Bindings

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate input history |
| `Tab` | Autocomplete slash command |
| `Escape` | Dismiss autocomplete suggestion list |
| `Ctrl+C` | Quit |

---

## Project Structure

```
tui/
├── app.py             # Main Textual application (UI, command dispatch, worker management)
├── commands.py        # Slash-command parser, registry, and autocomplete
├── event_handler.py   # Event Stream consumer (streams turns, extracts agent output)
├── harness.py         # CODEX Harness process manager (launch / stop codex exec-server)
├── history.py         # Input history persistence
├── session_manager.py # OpenAI session CRUD and turn send helpers
├── tools.py           # Function tool call dispatcher
└── __main__.py        # Entry point (python -m tui)
```

---

## Domain Glossary

| Term | Meaning |
|---|---|
| **Session** | A persistent conversation context created via `client.beta.agents.sessions.create(...)`, identified by a `session_id` |
| **Turn** | A single round-trip — one user message sent and the agent's response streamed until `agent.session.turn.completed` |
| **Environment** | The execution context attached to a Session: `none`, `self_hosted`, or `openai_hosted` |
| **CODEX Harness** | The `@openai/codex` binary (`codex exec-server`) launched as a child process; required for `openai_hosted` sessions |
| **Event Stream** | The server-sent stream of typed events received from `sessions.events.stream(session_id)` |
| **Agent Output** | Text content produced by the agent during a Turn, rendered prominently in the log |
| **System Event** | Lifecycle events from the Event Stream (e.g. `agent.session.idle`, `turn.completed`); shown muted, hidden in non-verbose mode |
| **Verbose Mode** | Toggle (via `/verbose`) to show all raw Event Stream events instead of just Agent Output and errors |

---

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Required. Used by the OpenAI Python client |
| `CODEX_API_KEY` | Required when using `openai_hosted` environment. Used by the CODEX harness process |

Create a `.env` file at the project root to set these:

```env
OPENAI_API_KEY=sk-...
CODEX_API_KEY=sk-...
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">Made with <a href="https://www.ibm.com/products/bob">IBM Bob</a></p>
