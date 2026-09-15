# Streaming session creation and event handler split

## Context

The OpenAI Agents API supports an optional `stream=True` parameter on
`sessions.create()`. When set, the call returns a `Stream[AgentSessionEvent]`
instead of an `AgentSession` object. The first event in that stream is always
`agent.session.created` and carries the full `AgentSession` payload (id,
environment, …). Any subsequent events belong to the initial Turn when an
`input` message was also supplied at creation time.

Two further needs arose from this:

1. The `/create-session` command should accept an optional initial message so
   the session and its first Turn can be submitted in a single API call.
2. The event-processing loop in `event_handler.py` was tightly coupled to
   opening a *new* stream via `sessions.events.stream()`, making it impossible
   to reuse it for an already-open stream returned by `sessions.create()`.

## Decision

**`SessionManager.create()` always passes `stream=True`.**  
It iterates the stream only until the `agent.session.created` event is received,
extracts the session id and environment from that event, and stores the
`ActiveSession`. If `config.input_text` is set, the still-open stream (which
contains the initial Turn events) is returned to the caller alongside the
`ActiveSession`. Otherwise the stream is closed immediately and `None` is
returned in its place. The return type is `Tuple[ActiveSession, Optional[Stream]]`.

**`event_handler` exposes two functions: `stream_events` and `stream_session`.**  
`stream_events(events, on_event)` accepts any iterable of session events and
processes them — no client or session id required. `stream_session` is now a
thin wrapper that opens a new stream via `sessions.events.stream()` and
delegates to `stream_events`. This lets the app feed the already-open stream
from `create()` through the same processing logic for the initial Turn.

**`AgentsApp` launches a dedicated `_stream_turn_from(events)` worker for the
initial Turn.**  
When `_cmd_create_session` receives a non-`None` stream back from `create()`,
it spawns `_stream_turn_from` (a `run_worker(thread=True)` worker) that calls
`stream_events` on the open stream. Subsequent Turns continue to use the
existing `_stream_turn` path via `stream_session`.

## Consequences

- The session id is always extracted from the stream, not from a synchronous
  response object, so the non-streaming path is no longer reachable from the
  TUI.
- The initial Turn is streamed with no extra round-trip: creation, input
  submission, and Turn streaming happen over a single HTTP connection.
- `stream_events` is independently testable with any iterable — no live API
  connection required.
- `SessionManager.create()` blocks the calling thread until
  `agent.session.created` arrives. Because `_cmd_create_session` is called on
  the main Textual thread (not inside a worker), there is a brief UI freeze
  while the server acknowledges the session. This is acceptable for now because
  session creation is a low-frequency, user-initiated action.

## Considered Options

- **Extract session id without `stream=True`** — keep the synchronous response
  for creation and only stream subsequent Turns via `sessions.events.stream()`.
  Rejected because `stream=True` is required to deliver the initial `input`
  message and receive its Turn events; without it the server processes the input
  but there is no stream to consume the response.
- **Run `create()` inside a worker and signal the session id back to the main
  thread** — would eliminate the brief UI freeze but requires a
  cross-thread signalling mechanism (e.g. a `threading.Event` or a Textual
  `Message`) and significantly complicates the session lifecycle. Deferred until
  the freeze becomes a real UX problem.
- **Keep a single `stream_session` function with an optional `events` parameter**
  — rejected because it conflates two distinct responsibilities (opening a
  stream vs. processing one) and makes the `client`/`session_id` parameters
  conditionally required, which is harder to type and test.
