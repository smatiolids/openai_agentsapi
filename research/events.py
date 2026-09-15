import argparse

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# Pass your saved session ID to this helper.
def stream_session(client: OpenAI, session_id: str, handle_event):
    with client.beta.agents.sessions.events.stream(session_id) as events:
        for event in events:
            handle_event(event)
            match event.type:
                case "agent.session.idle":
                    continue
                case "error":
                    raise RuntimeError(event.error.message)
                case "agent.session.failed" | "agent.session.environment.failed":
                    raise RuntimeError(f"Agent lifecycle failure: {event.type}")
                case "agent.session.turn.failed":
                    if event.turn.subagent_id is None:
                        detail = event.turn.error.message if event.turn.error else ""
                        raise RuntimeError(f"{event.type}: {detail}")
                case "agent.session.turn.cancelled":
                    if event.turn.subagent_id is None:
                        raise RuntimeError("The agent turn was cancelled")
                case "agent.session.turn.completed":
                    if event.turn.subagent_id is None:
                        return
    raise RuntimeError("Stream closed before a turn ended. Retrieve the saved state.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream events for an OpenAI Agents API session.")
    parser.add_argument("session_id", help="The ID of the session to stream")
    args = parser.parse_args()

    def print_event(event):
        print(event.to_json(indent=None), flush=True)

    stream_session(OpenAI(), args.session_id, print_event)