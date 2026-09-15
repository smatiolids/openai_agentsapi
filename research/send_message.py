import argparse

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def send_message(client: OpenAI, session_id: str, text: str) -> None:
    client.beta.agents.sessions.events.create(
        session_id,
        events=[
            {
                "type": "agent.session.input.message",
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": text,
                            }
                        ],
                    }
                ],
            }
        ],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a message to an OpenAI Agents API session.")
    parser.add_argument("session_id", help="The ID of the session to send the message to")
    parser.add_argument("text", help="The message text to send")
    args = parser.parse_args()

    send_message(OpenAI(), args.session_id, args.text)