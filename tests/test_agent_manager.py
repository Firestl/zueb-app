from __future__ import annotations

import unittest

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from bot.agent.client import AgentManager


class _FakeClient:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages
        self.queries: list[tuple[str, str]] = []

    async def query(self, prompt: str, *, session_id: str) -> None:
        self.queries.append((prompt, session_id))

    async def receive_response(self):
        for msg in self._messages:
            yield msg


class AgentManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_reset_session_rotates_session_id(self) -> None:
        manager = AgentManager()
        scope = "telegram-chat:1859552633"

        first = manager._resolve_session_id(scope)
        self.assertEqual(len(first), 32)
        self.assertNotIn(":", first)

        await manager.reset_session(scope)
        second = manager._resolve_session_id(scope)

        self.assertEqual(len(second), 32)
        self.assertNotIn(":", second)
        self.assertNotEqual(first, second)

    async def test_sync_session_id_uses_sdk_result(self) -> None:
        manager = AgentManager()
        scope = "telegram-chat:1859552633"
        requested = manager._resolve_session_id(scope)

        resolved = await manager._sync_session_id(
            session_scope=scope,
            requested_session_id=requested,
            resolved_session_id="server-session-123",
        )

        self.assertEqual(resolved, "server-session-123")
        self.assertEqual(manager._session_ids[scope], "server-session-123")

    async def test_sync_session_id_does_not_override_newer_mapping(self) -> None:
        manager = AgentManager()
        scope = "telegram-chat:1859552633"
        manager._session_ids[scope] = "newer-session"

        resolved = await manager._sync_session_id(
            session_scope=scope,
            requested_session_id="old-session",
            resolved_session_id="server-old-session",
        )

        self.assertEqual(resolved, "server-old-session")
        self.assertEqual(manager._session_ids[scope], "newer-session")

    async def test_collect_response_extracts_result_session_id(self) -> None:
        manager = AgentManager()
        fake_client = _FakeClient(
            messages=[
                AssistantMessage(content=[TextBlock(text="OK")], model="claude"),
                ResultMessage(
                    subtype="success",
                    duration_ms=1,
                    duration_api_ms=1,
                    is_error=False,
                    num_turns=1,
                    session_id="server-session-xyz",
                    result="fallback",
                ),
            ]
        )

        reply, chunks, resolved_session_id = await manager._collect_response(
            fake_client, "hello", "requested-session"
        )

        self.assertEqual(fake_client.queries, [("hello", "requested-session")])
        self.assertEqual(reply, "OK")
        self.assertEqual(chunks, 1)
        self.assertEqual(resolved_session_id, "server-session-xyz")


if __name__ == "__main__":
    unittest.main()
