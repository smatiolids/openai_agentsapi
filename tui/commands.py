"""Command parser and registry for slash-commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


HELP_TEXT = """\
Available commands:
  /set-environment <none|self|openai>   Set the environment type for the next session
  /set-model <model>                    Set the agent model (default: gpt-6-astra)
  /set-instructions <text>             Set the agent instructions
  /create-session [--web_search] [--tool_cep] [<initial message>]
                                       Create a new session; --web_search enables web search tool with low reasoning effort;
                                       --tool_cep registers the get_customer/CEP lookup function tool
  /connect-session <session_id>        Connect to an existing session by ID
  /delete-session                      Delete the active session
  /cancel-turn                         Cancel the active session's current turn
  /clear-sessions                      Delete all API sessions except the currently active one
  /list-sessions [<limit>]             List active sessions from the API (default limit: 20)
  /session-stats                       Show token usage summary for the active session
  /session-inspect                     Print all session attributes as copy-pasteable Python
  /harness-script                      Print the codex exec-server command for the active session's environment
  /list-codex                          List active codex exec-server processes
  /verbose                             Toggle verbose event display
  /exit                                Delete session, stop all processes and quit
  /help                                Show this help message

When a session is active, text without a leading / is sent as a message to the agent.\
"""


@dataclass
class ParsedCommand:
    name: str          # e.g. "set-environment"
    args: list[str]    # remaining tokens


def parse(text: str) -> Optional[ParsedCommand]:
    """
    Parse a slash-command from *text*.
    Returns None if *text* does not start with '/'.
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    tokens = stripped[1:].split(None, 1)  # split off first word only
    name = tokens[0].lower() if tokens else ""
    # Split the remainder into individual args
    args = tokens[1].split() if len(tokens) > 1 else []
    return ParsedCommand(name=name, args=args)


KNOWN_COMMANDS = {
    "set-environment",
    "set-model",
    "set-instructions",
    "create-session",
    "connect-session",
    "delete-session",
    "cancel-turn",
    "clear-sessions",
    "list-sessions",
    "session-stats",
    "session-inspect",
    "harness-script",
    "list-codex",
    "verbose",
    "exit",
    "help",
}

# Sorted list used for autocomplete
_SORTED_COMMANDS: list[str] = sorted(KNOWN_COMMANDS)


def is_known(name: str) -> bool:
    return name in KNOWN_COMMANDS


def completions(prefix: str) -> list[str]:
    """
    Return all known command names whose slash-form starts with *prefix*.

    *prefix* should include the leading slash, e.g. "/set".
    Returns an empty list when *prefix* does not start with '/'.
    """
    if not prefix.startswith("/"):
        return []
    fragment = prefix[1:].lower()
    return [cmd for cmd in _SORTED_COMMANDS if cmd.startswith(fragment)]
