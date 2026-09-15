import argparse
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def delete_session(client: OpenAI, session_id: str):
    return client.beta.agents.sessions.delete(session_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete an OpenAI Agents API session.")
    parser.add_argument("session_id", help="The ID of the session to delete")
    args = parser.parse_args()

    result = delete_session(OpenAI(), args.session_id)
    print(result.to_json())