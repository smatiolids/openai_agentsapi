# TUI architecture: Textual with run_worker for streaming

The TUI uses Textual as the UI framework. The OpenAI SDK's `events.stream()` is a blocking iterator; to keep the UI responsive during streaming, each Turn's stream is run inside a Textual `run_worker(thread=True)` worker. The worker posts messages to the app via `self.post_message` to update the log panel. This is the idiomatic Textual pattern for blocking I/O and avoids reimplementing thread-safe UI updates.

## Considered Options

- `asyncio.to_thread` directly — rejected because Textual's worker system handles cancellation, error propagation, and UI updates more cleanly than raw asyncio primitives.
- Async OpenAI SDK (`AsyncOpenAI`) — rejected because the existing research scripts are built around the sync SDK and the async client would require restructuring all existing code.
