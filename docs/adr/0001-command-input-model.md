# Command input model: slash-prefix with smart default

The TUI uses a single input field for both commands and free-text messages. When no session is active, all input is treated as a command. When a session is active, free text is sent directly to the agent via `send_message`; commands are prefixed with `/` (e.g. `/delete-session`, `/set-environment`). This eliminates the need for a separate command mode or a second screen, and matches the mental model of chat tools (Slack, IRC) that users already know.

## Considered Options

- Separate screens for setup vs. chat — rejected because it adds navigation overhead and splits context the user needs simultaneously.
- Always require a prefix — rejected because it forces the user to type `/send` for every message, which is the dominant action once a session exists.
