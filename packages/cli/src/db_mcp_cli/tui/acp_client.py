"""ACP insider agent client for TUI."""

from __future__ import annotations

import logging
from typing import Callable

from acp import Client, spawn_agent_process, text_block

logger = logging.getLogger(__name__)


class _TUIClient(Client):
    """ACP client that forwards session updates to a callback."""

    def __init__(self, on_update: Callable[[str], None] | None = None) -> None:
        self._on_update = on_update

    async def session_update(self, session_id, update, **kwargs):
        """Called by the agent when it has a status update."""
        text = ""
        if hasattr(update, "text"):
            text = update.text
        elif isinstance(update, dict):
            text = update.get("text", str(update))
        else:
            text = str(update)
        if text and self._on_update:
            self._on_update(text)

    async def request_permission(self, options, session_id, tool_call, **kwargs):
        """Auto-allow tool calls from the agent."""
        return {"outcome": {"outcome": "allow"}}


class ACPClient:
    """Manages an ACP agent subprocess and session."""

    def __init__(self, agent_command: str = "claude", mcp_url: str = "http://localhost:8080/mcp"):
        self.agent_command = agent_command
        self.mcp_url = mcp_url
        self.session_id: str | None = None
        self._conn = None
        self._process = None
        self._ctx = None

    async def prompt(self, text: str, on_update: Callable[[str], None] | None = None) -> None:
        """Send a prompt to the agent, spawning if needed."""
        if self._conn is None:
            await self._start(on_update)

        assert self._conn is not None
        assert self.session_id is not None

        await self._conn.prompt(
            [text_block(text)],
            session_id=self.session_id,
        )

    async def _start(self, on_update: Callable[[str], None] | None = None) -> None:
        """Spawn the agent process and create a session."""
        client = _TUIClient(on_update=on_update)
        self._ctx = spawn_agent_process(client, self.agent_command)
        self._conn, self._process = await self._ctx.__aenter__()

        await self._conn.initialize(protocol_version=1)
        session = await self._conn.new_session(
            cwd=".",
            mcp_servers=[{"url": self.mcp_url}],
        )
        self.session_id = session.session_id
        logger.info("ACP session started: %s (agent: %s)", self.session_id, self.agent_command)

    async def close(self) -> None:
        """Shut down the agent process."""
        if self._ctx is not None:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._conn = None
            self._process = None
            self._ctx = None
            self.session_id = None
