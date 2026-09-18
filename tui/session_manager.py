"""Session lifecycle management for the OpenAI Agents API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from openai import OpenAI
from openai._streaming import Stream

from tui.tools import CEP_TOOL_DEFINITION


@dataclass
class SessionStats:
    turns: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


@dataclass
class SessionConfig:
    model: str = "gpt-6-astra"
    instructions: str = "You are a helpful coding assistant. Write clean code and verify that it works."
    environment_type: str = "none"  # "none" | "self_hosted" | "openai_hosted"
    workspace_directory: str = "/tmp/openai_agent_workspace"
    input_text: str = ""  # optional first message sent when the session is created
    tools: list = field(default_factory=list)
    web_search: bool = False  # when True, add web_search tool + low reasoning effort
    tool_cep: bool = False    # when True, add CEP function tool


@dataclass
class ActiveSession:
    session_id: str
    config: SessionConfig
    environment_remote_url: Optional[str] = None
    environment_id: Optional[str] = None


class SessionManager:
    def __init__(self, client: OpenAI) -> None:
        self._client = client
        self._session: Optional[ActiveSession] = None

    @property
    def active(self) -> Optional[ActiveSession]:
        return self._session

    def create(self, config: SessionConfig) -> Tuple[ActiveSession, Optional[Stream]]:
        """
        Create a new session.

        Returns ``(ActiveSession, stream)`` where *stream* is the open
        ``Stream`` object when ``config.input_text`` was provided (the stream
        contains the initial turn events), or ``None`` otherwise.
        """
        if self._session is not None:
            raise RuntimeError("A session is already active. Delete it first.")

        env: dict
        if config.environment_type == "none":
            env = {"type": "none"}
        elif config.environment_type == "self_hosted":
            env = {"type": "self_hosted", "workspace_directory": config.workspace_directory}
        elif config.environment_type == "openai_hosted":
            env = {"type": "openai_hosted"}
        else:
            raise ValueError(f"Unknown environment type: {config.environment_type!r}")

        tools = list(config.tools)
        if config.web_search:
            tools.append({"type": "web_search", "mode": "live"})
        if config.tool_cep:
            tools.append(CEP_TOOL_DEFINITION)

        agent_dict: dict = {
            "model": config.model,
            "instructions": config.instructions,
            "tools": tools,
        }
        if config.web_search:
            agent_dict["reasoning"] = {"effort": "low"}

        create_kwargs: dict = dict(
            agent=agent_dict,
            environment=env,
            stream=True,
        )
        if config.input_text:
            create_kwargs["input"] = config.input_text

        stream: Stream = self._client.beta.agents.sessions.create(**create_kwargs)

        # The first event is always agent.session.created and carries the session id.
        session_obj = None
        for event in stream:
            if getattr(event, "type", "") == "agent.session.created":
                session_obj = event.session
                break

        if session_obj is None:
            stream.close()
            raise RuntimeError("Stream ended before agent.session.created was received.")

        env_id = None
        remote_url = None
        env_resource = getattr(session_obj, "environment", None)
        if env_resource is not None:
            env_id = getattr(env_resource, "id", None)
            remote_url = (
                getattr(env_resource, "remote_url", None)
                or getattr(env_resource, "remoteUrl", None)
            )

        self._session = ActiveSession(
            session_id=session_obj.id,
            config=config,
            environment_remote_url=remote_url,
            environment_id=env_id,
        )

        # Return the open stream only when there is an initial turn to drain.
        remaining_stream: Optional[Stream] = stream if config.input_text else None
        if not config.input_text:
            stream.close()

        return self._session, remaining_stream

    def session_stats(self, session_id: str) -> SessionStats:
        """Aggregate token usage across all turns for *session_id*."""
        stats = SessionStats()
        page = self._client.beta.agents.sessions.turns.list(
            session_id, limit=50, order="desc"
        )
        turns = list(page.data)
        while page.has_next_page():
            page = page.get_next_page()
            turns.extend(page.data)

        stats.turns = len(turns)
        for turn in turns:
            usage = getattr(turn, "usage", None)
            if usage is None:
                continue
            stats.input_tokens += getattr(usage, "input_tokens", 0) or 0
            stats.output_tokens += getattr(usage, "output_tokens", 0) or 0
            stats.total_tokens += getattr(usage, "total_tokens", 0) or 0
            input_details = getattr(usage, "input_tokens_details", None)
            if input_details is not None:
                stats.cached_tokens += getattr(input_details, "cached_tokens", 0) or 0
            output_details = getattr(usage, "output_tokens_details", None)
            if output_details is not None:
                stats.reasoning_tokens += getattr(output_details, "reasoning_tokens", 0) or 0
        return stats

    def attach(self, session_id: str) -> tuple[ActiveSession, object]:
        """
        Attach to an existing session by ID without creating a new one.

        Returns ``(ActiveSession, session_obj)`` where *session_obj* is the raw
        API object so callers can inspect its fields without a second round-trip.

        Raises ``RuntimeError`` if a session is already active or the session
        cannot be retrieved.
        """
        if self._session is not None:
            raise RuntimeError("A session is already active. Delete it first.")
        session_obj = self._client.beta.agents.sessions.retrieve(session_id)
        env_id = None
        remote_url = None
        env_resource = getattr(session_obj, "environment", None)
        if env_resource is not None:
            env_id = getattr(env_resource, "id", None)
            remote_url = (
                getattr(env_resource, "remote_url", None)
                or getattr(env_resource, "remoteUrl", None)
            )
        self._session = ActiveSession(
            session_id=session_obj.id,
            config=SessionConfig(),
            environment_remote_url=remote_url,
            environment_id=env_id,
        )
        return self._session, session_obj

    def retrieve_session(self, session_id: str):
        """Fetch the full AgentSession object from the API."""
        return self._client.beta.agents.sessions.retrieve(session_id)

    def list_sessions(self, limit: int = 20) -> list:
        """Return sessions from the API, following pagination up to *limit* total."""
        results = []
        page = self._client.beta.agents.sessions.list(limit=limit)
        results.extend(page.data)
        while page.has_next_page() and len(results) < limit:
            page = page.get_next_page()
            results.extend(page.data)
        return results[:limit]

    def delete_others(self) -> tuple[int, list[str]]:
        """Delete every API session except the currently active one.

        Returns ``(deleted_count, skipped_ids)`` where *skipped_ids* contains
        session IDs that failed to delete.
        """
        active_id = self._session.session_id if self._session else None
        page = self._client.beta.agents.sessions.list(limit=100)
        all_sessions = list(page.data)
        while page.has_next_page():
            page = page.get_next_page()
            all_sessions.extend(page.data)

        deleted = 0
        failed: list[str] = []
        for s in all_sessions:
            if s.id == active_id:
                continue
            try:
                self._client.beta.agents.sessions.delete(s.id)
                deleted += 1
            except Exception:
                failed.append(s.id)
        return deleted, failed

    def delete(self) -> None:
        if self._session is None:
            raise RuntimeError("No active session.")
        self._client.beta.agents.sessions.delete(self._session.session_id)
        self._session = None

    def send_message(self, text: str) -> None:
        if self._session is None:
            raise RuntimeError("No active session.")
        self._client.beta.agents.sessions.events.create(
            self._session.session_id,
            events=[
                {
                    "type": "agent.session.input.message",
                    "input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": text}],
                        }
                    ],
                }
            ],
        )
