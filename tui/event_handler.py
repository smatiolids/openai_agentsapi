"""Event stream handling — runs in a Textual worker thread."""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from openai import OpenAI


def stream_session(
    client: OpenAI,
    session_id: str,
    on_event: Callable[[str, str], None],
    on_requires_action: Optional[Callable[[list], None]] = None,
) -> None:
    """
    Open a new event stream for *session_id* and process it until the turn
    completes.  Delegates to ``stream_events``.

    *on_requires_action(actions)* is called when the session pauses for
    function results.  If omitted, the actions are only logged.
    """
    with client.beta.agents.sessions.events.stream(session_id) as events:
        stream_events(events, on_event, on_requires_action)


def stream_events(
    events: Iterable,
    on_event: Callable[[str, str], None],
    on_requires_action: Optional[Callable[[list], None]] = None,
) -> None:
    """
    Process an already-open event iterable until the turn completes.

    *on_event(kind, text)* is called for each event:
      - kind="output"  → agent output text
      - kind="system"  → lifecycle / status description
      - kind="error"   → error message
      - kind="raw"     → full JSON string (verbose mode, all events)

    *on_requires_action(actions)* is called when the session pauses waiting
    for function-call results.  If omitted, the pause is only logged.

    Raises RuntimeError on stream-level failures.
    """
    for event in events:
        raw_json = event.to_json(indent=None)
        event_type: str = getattr(event, "type", "")

        # Always emit raw for verbose consumers
        on_event("raw", raw_json)

        match event_type:
            case "agent.session.idle":
                on_event("system", "Session idle")

            case "agent.session.environment.connected":
                env = getattr(event, "environment", None)
                env_id = getattr(env, "id", None) if env else None
                detail = f"  environment_id={env_id}" if env_id else ""
                on_event("info", f"✓ Environment connected{detail}")

            case "agent.session.requires_action":
                session_obj = getattr(event, "session", None)
                actions = getattr(session_obj, "required_actions", []) if session_obj else []
                on_event("system", f"⚠ Session requires action ({len(actions)} pending):")
                for action in actions:
                    action_type = getattr(action, "type", "unknown")
                    if action_type == "environment_connection":
                        env_id = getattr(action, "environment_id", "?")
                        on_event("info", f"  environment_connection  environment_id={env_id}")
                        on_event("info", "  → Run the exec-server and use /harness-script for the command.")
                    elif action_type == "function_call":
                        name = getattr(action, "name", "?")
                        call_id = getattr(action, "call_id", "?")
                        turn_id = getattr(action, "turn_id", "?")
                        arguments = getattr(action, "arguments", None)
                        on_event("info", f"  function_call  name={name}  call_id={call_id}  turn_id={turn_id}")
                        if arguments:
                            on_event("info", f"  arguments: {arguments}")
                    else:
                        on_event("info", f"  {action_type}: {action.to_json() if hasattr(action, 'to_json') else action}")
                if on_requires_action is not None:
                    on_requires_action(actions)
                return  # session is paused — stop draining this stream

            case "error":
                msg = getattr(event, "error", None)
                error_text = msg.message if msg else raw_json
                on_event("error", error_text)
                raise RuntimeError(error_text)

            case "agent.session.failed" | "agent.session.environment.failed":
                on_event("error", f"Session lifecycle failure: {event_type}")
                raise RuntimeError(f"Agent lifecycle failure: {event_type}")

            case "agent.session.turn.failed":
                turn = getattr(event, "turn", None)
                if turn and getattr(turn, "subagent_id", None) is None:
                    err = getattr(turn, "error", None)
                    detail = err.message if err else ""
                    on_event("error", f"Turn failed: {detail}")
                    raise RuntimeError(f"{event_type}: {detail}")

            case "agent.session.turn.cancelled":
                turn = getattr(event, "turn", None)
                if turn and getattr(turn, "subagent_id", None) is None:
                    on_event("error", "Turn was cancelled")
                    raise RuntimeError("The agent turn was cancelled")

            case "agent.session.turn.completed":
                turn = getattr(event, "turn", None)
                if turn and getattr(turn, "subagent_id", None) is None:
                    on_event("system", "Turn completed")
                    return

            case _:
                # Extract agent output text if present
                output = _extract_output_text(event)
                if output:
                    on_event("output", output)
                else:
                    on_event("system", event_type)

    raise RuntimeError("Stream closed before a turn ended.")


def _extract_output_text(event) -> str | None:
    """
    Best-effort extraction of human-readable text from an event.
    Handles common shapes: event.content[].text, event.delta.text, event.text.
    """
    # delta text (streaming tokens)
    delta = getattr(event, "delta", None)
    if delta:
        text = getattr(delta, "text", None)
        if text:
            return text

    # content array
    content = getattr(event, "content", None)
    if content and isinstance(content, list):
        parts = []
        for item in content:
            t = getattr(item, "text", None)
            if t:
                parts.append(t)
        if parts:
            return "".join(parts)

    # direct text field
    text = getattr(event, "text", None)
    if text and isinstance(text, str):
        return text

    return None
