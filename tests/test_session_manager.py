"""Tests unitaires pour session_manager.py — Requirements 4.1, 4.2, 4.4, 4.5"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from session_manager import SessionManager, GRACE_PERIOD_SECONDS


class FakeWebSocket:
    """Simule un WebSocket avec send_text asynchrone."""

    def __init__(self, *, fail: bool = False):
        self.sent: list[str] = []
        self._fail = fail

    async def send_text(self, message: str) -> None:
        if self._fail:
            raise RuntimeError("WebSocket closed")
        self.sent.append(message)


class FakeTranscriptionSession:
    """Simule TranscriptionSession pour isoler les tests du SessionManager."""

    def __init__(self, on_message):
        self.on_message = on_message
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True
        # Simulate a long-running session that can be cancelled
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        self.stopped = True


@pytest.fixture
def manager():
    return SessionManager()


class TestConnect:
    @pytest.mark.asyncio
    async def test_first_client_starts_transcription(self, manager):
        """Req 4.1: Le premier client démarre la session de transcription."""
        ws = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws)

        assert ws in manager.clients
        assert manager.transcription_session is not None

    @pytest.mark.asyncio
    async def test_second_client_reuses_session(self, manager):
        """Req 4.1: Le deuxième client réutilise la session existante."""
        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws1)
            session = manager.transcription_session
            await manager.connect(ws2)

        assert manager.transcription_session is session
        assert len(manager.clients) == 2

    @pytest.mark.asyncio
    async def test_connect_cancels_grace_period(self, manager):
        """Req 4.2: Un nouveau client annule le délai de grâce."""
        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws1)
            await manager.disconnect(ws1)
            # Grace task should be scheduled
            assert manager._grace_task is not None
            grace_task = manager._grace_task

            await manager.connect(ws2)
            # Let the event loop process the cancellation
            await asyncio.sleep(0)
            assert grace_task.cancelled() or grace_task.done()
            assert manager.transcription_session is not None


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self, manager):
        ws = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws)
            await manager.disconnect(ws)

        assert ws not in manager.clients

    @pytest.mark.asyncio
    async def test_last_client_schedules_stop(self, manager):
        """Req 4.2: Le dernier client planifie l'arrêt avec délai de grâce."""
        ws = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws)
            await manager.disconnect(ws)

        assert manager._grace_task is not None
        assert not manager._grace_task.done()

    @pytest.mark.asyncio
    async def test_not_last_client_no_stop(self, manager):
        """Si d'autres clients restent, pas de délai de grâce."""
        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws1)
            await manager.connect(ws2)
            await manager.disconnect(ws1)

        assert manager._grace_task is None
        assert len(manager.clients) == 1

    @pytest.mark.asyncio
    async def test_disconnect_unknown_client_no_error(self, manager):
        """Déconnecter un client inconnu ne lève pas d'erreur."""
        ws = FakeWebSocket()
        await manager.disconnect(ws)  # Should not raise


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self, manager):
        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()
        manager.clients = [ws1, ws2]

        await manager.broadcast('{"type":"status","status":"connected","message":"ok"}')

        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_clients(self, manager):
        """Les clients morts sont retirés silencieusement."""
        ws_ok = FakeWebSocket()
        ws_dead = FakeWebSocket(fail=True)
        manager.clients = [ws_ok, ws_dead]

        await manager.broadcast('{"type":"status","status":"connected","message":"ok"}')

        assert ws_ok in manager.clients
        assert ws_dead not in manager.clients
        assert len(ws_ok.sent) == 1

    @pytest.mark.asyncio
    async def test_broadcast_empty_clients(self, manager):
        """Broadcast sans clients ne lève pas d'erreur."""
        await manager.broadcast('{"type":"status","status":"connected","message":"ok"}')


class TestGracePeriod:
    @pytest.mark.asyncio
    async def test_grace_period_stops_session(self, manager):
        """Req 4.2: Après le délai de grâce, la session est arrêtée."""
        ws = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws)
            await manager.disconnect(ws)

            # Fast-forward: patch sleep to return immediately
            with patch("session_manager.asyncio.sleep", new_callable=AsyncMock):
                await manager._grace_task

        assert manager.transcription_session is None


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cleans_everything(self, manager):
        ws = FakeWebSocket()
        with patch("session_manager.TranscriptionSession", FakeTranscriptionSession):
            await manager.connect(ws)
            await manager.shutdown()

        assert manager.transcription_session is None
        assert len(manager.clients) == 0
