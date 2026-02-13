"""
Gestionnaire de sessions WebSocket.

Maintient la liste des clients connectés, gère le cycle de vie
d'une session de transcription partagée unique, et diffuse les
messages à tous les clients.
"""

import asyncio
import logging
from typing import Any

from messages import StatusMessage, serialize
from transcription_session import TranscriptionSession

logger = logging.getLogger(__name__)

GRACE_PERIOD_SECONDS = 30


class SessionManager:
    """Gère les connexions WebSocket et la session de transcription partagée."""

    def __init__(self) -> None:
        self.clients: list[Any] = []
        self.transcription_session: TranscriptionSession | None = None
        self._grace_task: asyncio.Task | None = None
        self._transcription_task: asyncio.Task | None = None

    async def connect(self, websocket: Any) -> None:
        """Ajoute un client et démarre la transcription si premier client.

        Si un délai de grâce est en cours (arrêt planifié), il est annulé.
        """
        self.clients.append(websocket)
        logger.info("Client connecté (%d client(s) actif(s))", len(self.clients))

        # Annuler le délai de grâce si en cours
        if self._grace_task is not None and not self._grace_task.done():
            self._grace_task.cancel()
            self._grace_task = None
            logger.info("Délai de grâce annulé — nouveau client connecté")

        # Démarrer la transcription si premier client
        if self.transcription_session is None:
            await self._start_transcription()

    async def disconnect(self, websocket: Any) -> None:
        """Retire un client et planifie l'arrêt si plus aucun client."""
        if websocket in self.clients:
            self.clients.remove(websocket)
        logger.info("Client déconnecté (%d client(s) restant(s))", len(self.clients))

        # Planifier l'arrêt si plus aucun client
        if len(self.clients) == 0 and self.transcription_session is not None:
            self._grace_task = asyncio.create_task(self._schedule_stop())

    async def broadcast(self, message: str) -> None:
        """Envoie un message (JSON sérialisé) à tous les clients connectés.

        Les clients morts (erreur d'envoi) sont retirés silencieusement.
        """
        dead_clients = []
        for client in self.clients:
            try:
                await client.send_text(message)
            except Exception:
                dead_clients.append(client)

        for client in dead_clients:
            if client in self.clients:
                self.clients.remove(client)

    async def _start_transcription(self) -> None:
        """Démarre une nouvelle session de transcription."""
        logger.info("Démarrage de la session de transcription")
        self.transcription_session = TranscriptionSession(on_message=self.broadcast)
        self._transcription_task = asyncio.create_task(self.transcription_session.start())

    async def _schedule_stop(self) -> None:
        """Attend le délai de grâce puis arrête la transcription si aucun client."""
        logger.info("Délai de grâce de %ds avant arrêt de la transcription", GRACE_PERIOD_SECONDS)
        try:
            await asyncio.sleep(GRACE_PERIOD_SECONDS)
        except asyncio.CancelledError:
            logger.info("Délai de grâce annulé")
            return

        # Vérifier qu'il n'y a toujours aucun client
        if len(self.clients) == 0 and self.transcription_session is not None:
            logger.info("Arrêt de la transcription — aucun client connecté")
            await self.transcription_session.stop()
            self.transcription_session = None
            if self._transcription_task and not self._transcription_task.done():
                self._transcription_task.cancel()
                try:
                    await self._transcription_task
                except asyncio.CancelledError:
                    pass
            self._transcription_task = None

    async def shutdown(self) -> None:
        """Arrêt propre : stoppe la transcription et ferme toutes les connexions."""
        if self._grace_task and not self._grace_task.done():
            self._grace_task.cancel()
            self._grace_task = None

        if self.transcription_session is not None:
            await self.transcription_session.stop()
            self.transcription_session = None

        if self._transcription_task and not self._transcription_task.done():
            self._transcription_task.cancel()
            try:
                await self._transcription_task
            except asyncio.CancelledError:
                pass
            self._transcription_task = None

        self.clients.clear()
