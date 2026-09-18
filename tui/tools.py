"""Built-in tool implementations called when the agent issues a function_call."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from openai import OpenAI


# ── Tool definition sent to the API ─────────────────────────────────────────

CEP_TOOL_DEFINITION: dict = {
    "type": "function",
    "name": "get_address",
    "description": "Look up an address by Brazilian postal code (CEP).",
    "parameters": {
        "type": "object",
        "properties": {"cep": {"type": "string"}},
        "required": ["cep"],
        "additionalProperties": False,
    },
}


# ── Implementation ────────────────────────────────────────────────────────────

def get_address(cep: str) -> dict:
    """
    Fetch address data for *cep* from the ViaCEP public API.

    Returns the parsed JSON dict on success.
    Raises ``ValueError`` if the CEP is not found or the response signals an error.
    Raises ``urllib.error.URLError`` on network failures.
    """
    cep_digits = cep.replace("-", "").strip()
    url = f"https://viacep.com.br/ws/{cep_digits}/json/"
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode())
    if data.get("erro"):
        raise ValueError(f"CEP not found: {cep!r}")
    return data


# ── Registry — maps tool name → callable(**arguments) → JSON-serialisable ───

FUNCTION_REGISTRY: dict[str, Callable] = {
    "get_address": lambda cep, **_: get_address(cep),
}


# ── Dispatcher ───────────────────────────────────────────────────────────────

def dispatch_function_calls(
    client: OpenAI,
    session_id: str,
    actions: list,
    on_event: Callable[[str, str], None],
) -> None:
    """
    Execute every ``function_call`` action in *actions* and submit the results
    back to the session as ``agent.session.tool_call.output`` events.

    *on_event* is the same logging callback used by the event stream.
    Unknown function names are submitted as an error string so the agent can
    handle them gracefully rather than hanging.
    """
    result_events = []
    for action in actions:
        if getattr(action, "type", "") != "function_call":
            continue

        name = getattr(action, "name", "")
        call_id = getattr(action, "call_id", "")
        turn_id = getattr(action, "turn_id", "")
        raw_args = getattr(action, "arguments", {})
        # arguments may arrive as a dict or a JSON string
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
        else:
            args = dict(raw_args) if raw_args else {}

        on_event("system", f"→ calling {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")

        fn = FUNCTION_REGISTRY.get(name)
        if fn is None:
            output = json.dumps({"error": f"Unknown function: {name!r}"})
            on_event("error", f"No implementation for function {name!r}")
        else:
            try:
                result = fn(**args)
                output = json.dumps(result, ensure_ascii=False)
                on_event("info", f"← {name} returned {output[:120]}{'…' if len(output) > 120 else ''}")
            except Exception as exc:
                output = json.dumps({"error": str(exc)})
                on_event("error", f"← {name} raised: {exc}")

        event: dict = {
            "type": "agent.session.input.tool_result",
            "call_id": call_id,
            "turn_id": turn_id,
            "success": fn is not None and not output.startswith('{"error":'),
            "output": output,
        }
        result_events.append(event)

    if result_events:
        client.beta.agents.sessions.events.create(session_id, events=result_events)
