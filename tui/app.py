"""Main Textual application."""

from __future__ import annotations

from dotenv import load_dotenv
from openai import OpenAI
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer, Header, Input, LoadingIndicator, Log, OptionList
from textual.widgets.option_list import Option
from textual.worker import Worker, WorkerState, get_current_worker

from tui import commands
from tui.event_handler import stream_events, stream_session
from tui.harness import HarnessManager
from tui import history as history_file
from tui.session_manager import ActiveSession, SessionConfig, SessionManager

load_dotenv()


def _common_prefix(words: list[str]) -> str:
    """Return the longest string that is a prefix of every word in *words*."""
    if not words:
        return ""
    prefix = words[0]
    for word in words[1:]:
        while not word.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


# ── Textual messages (posted from worker thread → main thread) ──────────────

class LogEvent(Message):
    """Carries a (kind, text) pair to append to the log."""
    def __init__(self, kind: str, text: str) -> None:
        super().__init__()
        self.kind = kind
        self.text = text


# ── App ──────────────────────────────────────────────────────────────────────

class AgentsApp(App):
    """OpenAI Agents API TUI."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #log {
        border: solid $primary;
        height: 1fr;
        margin: 0 1;
    }

    #loading {
        height: 1;
        margin: 0 2;
        display: none;
    }

    #suggest {
        height: auto;
        max-height: 10;
        margin: 0 1;
        display: none;
    }

    #input {
        margin: 0 1 1 1;
        height: 3;
    }

    .output  { color: $text; }
    .system  { color: $text-muted; }
    .error   { color: $error; }
    .raw     { color: $text-disabled; }
    .info    { color: $accent; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("up", "history_up", "History up", show=False, priority=True),
        Binding("down", "history_down", "History down", show=False, priority=True),
        Binding("tab", "autocomplete", "Autocomplete", show=False, priority=True),
        Binding("escape", "dismiss_suggest", "Dismiss", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._client = OpenAI()
        self._session_mgr = SessionManager(self._client)
        self._harness_mgr = HarnessManager()
        self._config = SessionConfig()
        self._verbose = False
        self._stream_worker: Worker | None = None
        self._history: list[str] = history_file.load()  # persisted + in-session entries
        self._history_pos: int = -1     # -1 = not browsing; 0 = oldest
        self._history_draft: str = ""   # saved current draft while browsing
        self._last_log_line: str = ""   # last line written to the log widget
        self._last_log_count: int = 0   # how many times it has repeated

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="log", highlight=True)
        yield LoadingIndicator(id="loading")
        yield OptionList(id="suggest")
        yield Input(
            id="input",
            placeholder="Type a message or /command…",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._log("info", "OpenAI Agents API TUI — type /help for commands")
        self._log("info", f"Config: model={self._config.model}  env={self._config.environment_type}")
        self.query_one("#input", Input).focus()

    # ── Input handling ───────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        """Rebuild the suggestion list as the user types."""
        self._update_suggest(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        self._update_suggest("")
        if not text:
            return

        # Push to history (skip duplicates of the last entry)
        if not self._history or self._history[-1] != text:
            self._history.append(text)
            history_file.append(text)
        self._history_pos = -1
        self._history_draft = ""

        if text.startswith("/"):
            self._handle_command(text)
        else:
            self._handle_message(text)

    def _input_focused(self) -> bool:
        return self.query_one("#input", Input).has_focus

    def action_history_up(self) -> None:
        if not self._input_focused():
            return
        input_widget = self.query_one("#input", Input)
        if not self._history:
            return
        if self._history_pos == -1:
            self._history_draft = input_widget.value
            self._history_pos = len(self._history) - 1
        elif self._history_pos > 0:
            self._history_pos -= 1
        self._set_input_history(input_widget, self._history[self._history_pos])

    def action_history_down(self) -> None:
        if not self._input_focused():
            return
        input_widget = self.query_one("#input", Input)
        if self._history_pos == -1:
            return
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self._set_input_history(input_widget, self._history[self._history_pos])
        else:
            self._history_pos = -1
            self._set_input_history(input_widget, self._history_draft)
            self._history_draft = ""

    def _set_input_history(self, input_widget: Input, value: str) -> None:
        """Set input value from history and suppress the autocomplete list."""
        input_widget.value = value
        input_widget.cursor_position = len(value)
        self.query_one("#suggest", OptionList).display = False

    def action_autocomplete(self) -> None:
        if not self._input_focused():
            return
        self._do_autocomplete(self.query_one("#input", Input))

    def action_dismiss_suggest(self) -> None:
        suggest = self.query_one("#suggest", OptionList)
        if self._input_focused() and suggest.display:
            suggest.display = False

    # ── Autocomplete helpers ─────────────────────────────────────────────────

    def _update_suggest(self, value: str) -> None:
        """Rebuild the OptionList with current completions."""
        suggest = self.query_one("#suggest", OptionList)
        matches = commands.completions(value) if value.startswith("/") else []
        # Only show while the command name is still being typed (no space yet)
        if matches and " " not in value[1:]:
            suggest.clear_options()
            for m in matches:
                suggest.add_option(Option(f"/{m}", id=m))
            suggest.highlighted = 0
            suggest.display = True
        else:
            suggest.display = False

    def _accept_suggestion(self, input_widget: Input, suggest: OptionList) -> None:
        """Fill the input with the highlighted suggestion and hide the list."""
        idx = suggest.highlighted
        if idx is None:
            return
        option = suggest.get_option_at_index(idx)
        input_widget.value = option.prompt + " "
        input_widget.cursor_position = len(input_widget.value)
        suggest.display = False

    def _do_autocomplete(self, input_widget: Input) -> None:
        """Tab: accept highlighted suggestion, or extend to longest common prefix."""
        suggest = self.query_one("#suggest", OptionList)
        if suggest.display and suggest.highlighted is not None:
            self._accept_suggestion(input_widget, suggest)
            return
        value = input_widget.value
        if not value.startswith("/") or " " in value[1:]:
            return
        matches = commands.completions(value)
        if not matches:
            return
        if len(matches) == 1:
            input_widget.value = f"/{matches[0]} "
        else:
            common = _common_prefix(matches)
            if len(common) > len(value) - 1:
                input_widget.value = f"/{common}"
        input_widget.cursor_position = len(input_widget.value)
        self._update_suggest(input_widget.value)

    # ── Command dispatch ─────────────────────────────────────────────────────

    def _handle_command(self, text: str) -> None:
        parsed = commands.parse(text)
        if parsed is None or not commands.is_known(parsed.name):
            self._log("error", f"Unknown command: {text!r}. Type /help for commands.")
            return

        match parsed.name:
            case "help":
                self._log("info", commands.HELP_TEXT)

            case "verbose":
                self._verbose = not self._verbose
                state = "ON" if self._verbose else "OFF"
                self._log("info", f"Verbose mode {state}")

            case "set-environment":
                if not parsed.args:
                    self._log("error", "Usage: /set-environment <none|self|openai>")
                    return
                env = parsed.args[0].lower()
                if env not in ("none", "self", "openai"):
                    self._log("error", "Environment must be: none, self, or openai")
                    return
                # Normalise "self" → "self_hosted", "openai" → "openai_hosted"
                mapping = {"none": "none", "self": "self_hosted", "openai": "openai_hosted"}
                self._config.environment_type = mapping[env]
                self._log("info", f"Environment set to: {self._config.environment_type}")

            case "set-model":
                if not parsed.args:
                    self._log("error", "Usage: /set-model <model>")
                    return
                self._config.model = parsed.args[0]
                self._log("info", f"Model set to: {self._config.model}")

            case "set-instructions":
                if not parsed.args:
                    self._log("error", "Usage: /set-instructions <text>")
                    return
                self._config.instructions = " ".join(parsed.args)
                self._log("info", f"Instructions set to: {self._config.instructions!r}")

            case "create-session":
                initial = " ".join(parsed.args) if parsed.args else ""
                self._run_command(lambda: self._cmd_create_session(initial))

            case "delete-session":
                self._run_command(self._cmd_delete_session)

            case "delete-other-sessions":
                self._run_command(self._cmd_delete_other_sessions)

            case "session-stats":
                self._run_command(self._cmd_session_stats)

            case "session-inspect":
                self._run_command(self._cmd_session_inspect)

            case "list-sessions":
                limit = int(parsed.args[0]) if parsed.args else 20
                self._run_command(lambda: self._cmd_list_sessions(limit))

            case "harness-script":
                self._cmd_harness_script()

            case "list-codex":
                self._cmd_list_codex()

            case "exit":
                self._cmd_exit()

    def _cmd_create_session(self, initial: str = "") -> None:
        if self._session_mgr.active:
            self._log("error", "A session is already active. Use /delete-session first.")
            return
        self._config.input_text = initial
        self._log("system", "Creating session…")
        try:
            session, init_stream = self._session_mgr.create(self._config)
        except Exception as exc:
            self._log("error", f"Failed to create session: {exc}")
            return

        self._log("info", f"Session created: {session.session_id}")

        if self._config.environment_type == "openai_hosted":
            if not session.environment_remote_url or not session.environment_id:
                self._log("error", "openai_hosted session missing remote_url / environment_id")
                return
            self._log("system", "Launching CODEX harness…")
            try:
                self._harness_mgr.start(
                    session_id=session.session_id,
                    remote_url=session.environment_remote_url,
                    environment_id=session.environment_id,
                )
                self._log("info", "CODEX harness started.")
            except Exception as exc:
                self._log("error", f"Failed to start CODEX harness: {exc}")

        session_id = session.session_id
        self.call_from_thread(setattr, self, "sub_title", f"session: {session_id[:12]}…")

        if init_stream is not None:
            self._log("output", f"You: {initial}")
            self.call_from_thread(
                lambda: setattr(
                    self,
                    "_stream_worker",
                    self.run_worker(
                        lambda: self._stream_turn_from(init_stream),
                        thread=True,
                        name="stream-turn",
                    ),
                )
            )

    def _cmd_delete_session(self) -> None:
        session = self._session_mgr.active
        if session is None:
            self._log("error", "No active session.")
            return
        # Stop any running stream worker
        if self._stream_worker and self._stream_worker.is_running:
            self._stream_worker.cancel()
        self._harness_mgr.stop(session.session_id)
        try:
            self._session_mgr.delete()
        except Exception as exc:
            self._log("error", f"Failed to delete session: {exc}")
            return
        self._log("info", "Session deleted.")
        self.call_from_thread(setattr, self, "sub_title", "")

    def _cmd_delete_other_sessions(self) -> None:
        active = self._session_mgr.active
        qualifier = f" (keeping active: {active.session_id[:12]}…)" if active else ""
        self._log("system", f"Deleting all other sessions{qualifier}…")
        try:
            deleted, failed = self._session_mgr.delete_others()
        except Exception as exc:
            self._log("error", f"Failed to delete sessions: {exc}")
            return
        self._log("info", f"Deleted {deleted} session(s).")
        for sid in failed:
            self._log("error", f"  Failed to delete: {sid}")

    def _cmd_exit(self) -> None:
        """Delete the active session, stop all harness processes, and quit."""
        if self._session_mgr.active:
            if self._stream_worker and self._stream_worker.is_running:
                self._stream_worker.cancel()
            self._harness_mgr.stop_all()
            try:
                self._session_mgr.delete()
            except Exception as exc:
                self._log("error", f"Failed to delete session: {exc}")
        else:
            self._harness_mgr.stop_all()
        self._log("info", "Bye!")
        self.exit()

    def _cmd_session_stats(self) -> None:
        session = self._session_mgr.active
        if session is None:
            self._log("error", "No active session.")
            return
        try:
            stats = self._session_mgr.session_stats(session.session_id)
        except Exception as exc:
            self._log("error", f"Failed to fetch session stats: {exc}")
            return
        self._log("info", f"Session stats — {session.session_id}")
        self._log("info", f"  Turns            : {stats.turns}")
        self._log("info", f"  Input tokens     : {stats.input_tokens}  (cached: {stats.cached_tokens})")
        self._log("info", f"  Output tokens    : {stats.output_tokens}  (reasoning: {stats.reasoning_tokens})")
        self._log("info", f"  Total tokens     : {stats.total_tokens}")

    def _cmd_session_inspect(self) -> None:
        session = self._session_mgr.active
        if session is None:
            self._log("error", "No active session.")
            return
        try:
            obj = self._session_mgr.retrieve_session(session.session_id)
        except Exception as exc:
            self._log("error", f"Failed to retrieve session: {exc}")
            return
        sid = session.session_id
        json_str = obj.model_dump_json(indent=2)
        snippet = (
            "from openai import OpenAI\n"
            "\n"
            "client = OpenAI()\n"
            f'session = client.beta.agents.sessions.retrieve("{sid}")\n'
            "print(session.model_dump_json(indent=2))\n"
            "\n"
            "# Live attributes snapshot:\n"
            + "\n".join(f"# {l}" for l in json_str.splitlines())
        )
        for line in snippet.splitlines():
            self._log("output", line)

    def _cmd_list_sessions(self, limit: int = 20) -> None:
        self._log("system", f"Fetching up to {limit} sessions…")
        try:
            sessions = self._session_mgr.list_sessions(limit)
        except Exception as exc:
            self._log("error", f"Failed to list sessions: {exc}")
            return
        if not sessions:
            self._log("info", "No sessions found.")
            return
        for s in sessions:
            self._log("info", f"  id={s.id}  status={getattr(s, 'status', '?')}")

    def _cmd_harness_script(self) -> None:
        import os
        session = self._session_mgr.active
        if session is None:
            self._log("error", "No active session. Create one with /create-session first.")
            return
        if not session.environment_remote_url or not session.environment_id:
            self._log("error", "Active session has no environment — create the session with /set-environment openai first.")
            return
        remote_url = session.environment_remote_url
        env_id = session.environment_id
        sid = session.session_id
        codex_api_key = os.environ.get("CODEX_API_KEY", "")
        key_line = (
            f'CODEX_API_KEY="{codex_api_key}" \\\n'
            if codex_api_key
            else '# CODEX_API_KEY not found in .env — set it before running\n'
        )
        script = (
            f"#!/usr/bin/env bash\n"
            f"# CODEX exec-server for session {sid}\n"
            f"# Run this in a separate terminal and leave it running while the agent works.\n"
            f"\n"
            f"{key_line}"
            f"codex exec-server \\\n"
            f'  --remote "{remote_url}" \\\n'
            f'  --environment-id "{env_id}"\n'
        )
        self._log("output", "── harness_script.sh ─────────────────────────────")
        for line in script.splitlines():
            self._log("output", line)
        self._log("output", "──────────────────────────────────────────────────")
        self._log("system", "Keep the executor running while the agent works.")

    def _cmd_list_codex(self) -> None:
        active = self._harness_mgr.list_active()
        if not active:
            self._log("info", "No active CODEX harness processes.")
            return
        for h in active:
            self._log("info", f"  codex exec-server  session={h.session_id}  env={h.environment_id}  pid={h.process.pid}")

    # ── Message (send to agent) ───────────────────────────────────────────────

    def _handle_message(self, text: str) -> None:
        session = self._session_mgr.active
        if session is None:
            self._log("error", "No active session. Use /create-session first.")
            return
        if self._stream_worker and self._stream_worker.is_running:
            self._log("error", "Agent is still processing the previous message.")
            return

        self._log("output", f"You: {text}")
        try:
            self._session_mgr.send_message(text)
        except Exception as exc:
            self._log("error", f"Failed to send message: {exc}")
            return

        self._stream_worker = self.run_worker(
            lambda: self._stream_turn(session),
            thread=True,
            name="stream-turn",
        )

    def _stream_turn(self, session: ActiveSession) -> None:
        """Runs in a worker thread. Posts LogEvent messages to the app."""
        worker = get_current_worker()

        def on_event(kind: str, text: str) -> None:
            if worker.is_cancelled:
                return
            self.post_message(LogEvent(kind=kind, text=text))

        try:
            stream_session(self._client, session.session_id, on_event)
        except Exception as exc:
            self.post_message(LogEvent(kind="error", text=str(exc)))

    def _stream_turn_from(self, events) -> None:
        """Runs in a worker thread. Drains an already-open stream."""
        worker = get_current_worker()

        def on_event(kind: str, text: str) -> None:
            if worker.is_cancelled:
                return
            self.post_message(LogEvent(kind=kind, text=text))

        try:
            stream_events(events, on_event)
        except Exception as exc:
            self.post_message(LogEvent(kind="error", text=str(exc)))

    # ── Worker state → loading indicator ────────────────────────────────────

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name not in ("stream-turn", "command"):
            return
        loading = self.query_one("#loading", LoadingIndicator)
        # Show spinner whenever either worker is running
        loading.display = (
            event.state == WorkerState.RUNNING
            or any(
                w.name in ("stream-turn", "command") and w.state == WorkerState.RUNNING
                for w in self.workers
                if w is not event.worker
            )
        )

    def _run_command(self, fn) -> None:
        """Run *fn* in a thread worker so the UI stays responsive and the
        loading indicator is shown while it executes."""
        self.run_worker(fn, thread=True, name="command")

    # ── LogEvent handler ─────────────────────────────────────────────────────

    def on_log_event(self, event: LogEvent) -> None:
        if event.kind == "raw":
            if self._verbose:
                self._write_log("raw", event.text)
        else:
            self._write_log(event.kind, event.text)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, kind: str, text: str) -> None:
        """Thread-safe log: routes through post_message so it works from workers."""
        self.post_message(LogEvent(kind=kind, text=text))

    def _write_log(self, kind: str, text: str) -> None:
        """Direct widget write — only called on the main thread via on_log_event."""
        log = self.query_one("#log", Log)
        prefix_map = {
            "output": "",
            "system": "[SYS] ",
            "error":  "[ERR] ",
            "raw":    "[RAW] ",
            "info":   "[INF] ",
        }
        prefix = prefix_map.get(kind, "")
        line = f"{prefix}{text}"

        if line == self._last_log_line:
            # Repeated line — overwrite the last entry with a counter
            self._last_log_count += 1
            if log._lines:
                log._lines[-1] = f"{line}  (×{self._last_log_count + 1})"
                log.refresh()
            return

        self._last_log_line = line
        self._last_log_count = 0
        log.write_line(line)

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def on_unmount(self) -> None:
        self._harness_mgr.stop_all()
