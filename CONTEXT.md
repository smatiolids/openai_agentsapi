# OpenAI Agents API TUI

A terminal user interface (built with Textual) for interacting with the OpenAI Agents API. Supports creating sessions, sending messages, streaming events, and launching the CODEX harness as a subprocess when required.

## Language

**Session**:
A persistent conversation context created via `client.beta.agents.sessions.create(...)`. Identified by a `session_id`. The TUI holds at most one active Session at a time.
_Avoid_: conversation, thread, run

**Turn**:
A single round-trip within a Session — one user message sent and the agent's response streamed back until `agent.session.turn.completed` is received. Implemented as: `send_message` → `stream_session` in sequence.
_Avoid_: exchange, request, interaction

**Environment**:
The execution context attached to a Session. One of three types: `none` (no execution), `self_hosted` (local workspace directory), or `openai_hosted` (remote sandbox managed by OpenAI).
_Avoid_: workspace, sandbox, runtime

**CODEX Harness**:
The `@openai/codex` npm binary (`codex exec-server`) launched as a child process by the TUI. Required only when the Session's Environment type is `openai_hosted`. Receives `remote_url` and `environment_id` from the Session object. Launched automatically on `/create-session` when environment is `openai_hosted`; killed automatically on `/delete-session`.
_Avoid_: codex agent, codex process, harness process

**Event Stream**:
The server-sent stream of typed events received from `client.beta.agents.sessions.events.stream(session_id)`. Carries turn lifecycle events (`turn.completed`, `turn.failed`, `turn.cancelled`), session lifecycle events, and agent output. Opened per Turn and closed after `turn.completed`.
_Avoid_: SSE, event loop, response stream

**Agent Output**:
The text content produced by the agent during a Turn, extracted from the Event Stream and rendered in the log panel. Displayed distinctly from system events.
_Avoid_: response, reply, message

**System Event**:
A lifecycle event from the Event Stream that is not Agent Output — e.g. `agent.session.idle`, `turn.completed`, `error`. Displayed in the log with a muted style to distinguish from Agent Output. Suppressed in non-verbose mode except for errors.
_Avoid_: internal event, metadata event

**Verbose Mode**:
A toggle (activated via `/verbose`) that switches the log between showing only Agent Output + errors, and showing all raw Event Stream events. Off by default.
_Avoid_: debug mode, raw mode
