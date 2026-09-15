
import os

from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

session = client.beta.agents.sessions.create(
    agent={
        "model": "gpt-6-astra",
        "instructions": "You are a helpful coding assistant. Write clean code and verify that it works.",
    },
    #environment={"type": "self_hosted", "workspace_directory": "/tmp/openai_agent_workspace"},
    environment={"type": "none"},
)
print(session.to_json())