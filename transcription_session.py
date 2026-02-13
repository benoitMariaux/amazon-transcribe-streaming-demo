"""
Session de transcription en temps réel.

Gère le pipeline audio ffmpeg et le client Amazon Transcribe Streaming.
Convertit les événements de transcription en messages structurés et les
diffuse via un callback asynchrone.
"""

import asyncio
import logging
import subprocess
from datetime import datetime, timezone
from typing import Awaitable, Callable

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

from messages import StatusMessage, TranscriptionMessage, serialize

logger = logging.getLogger(__name__)

# Configuration
STREAM_URL = "http://icecast.radiofrance.fr/franceinfo-lofi.aac"
LANGUAGE_CODE = "fr-FR"
SAMPLE_RATE = 16000
REGION = "us-east-1"
CHUNK_SIZE = 1024 * 4  # 4KB chunks
RECONNECT_DELAY_SECONDS = 5


class _TranscriptHandler(TranscriptResultStreamHandler):
    """Gère les événements de transcription et appelle le callback on_message."""

    def __init__(self, output_stream, on_message: Callable[[dict], Awaitable[None]]):
        super().__init__(output_stream)
        self._on_message = on_message

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                transcript = alt.transcript.strip()
                if not transcript:
                    continue

                now = datetime.now(timezone.utc).isoformat()
                if result.is_partial:
                    msg = TranscriptionMessage(type="partial", text=transcript, timestamp=now)
                else:
                    msg = TranscriptionMessage(type="final", text=transcript, timestamp=now)

                await self._on_message(serialize(msg))


class TranscriptionSession:
    """
    Session de transcription en temps réel.

    Gère le cycle de vie du pipeline audio ffmpeg et du client
    Amazon Transcribe Streaming. Diffuse les résultats via le
    callback on_message.
    """

    def __init__(self, on_message: Callable[[dict], Awaitable[None]]):
        self.on_message = on_message
        self.is_active: bool = False
        self._ffmpeg_process: subprocess.Popen | None = None
        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._reader_task: asyncio.Task | None = None
        self._transcribe_task: asyncio.Task | None = None

    def _start_ffmpeg(self) -> None:
        """Lance le processus ffmpeg pour capturer le flux Icecast en PCM 16kHz mono."""
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", STREAM_URL,
            "-ar", str(SAMPLE_RATE),
            "-ac", "1",
            "-f", "s16le",
            "-",
        ]
        self._ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8,
        )
        logger.info("ffmpeg démarré (PID %s)", self._ffmpeg_process.pid)

    async def _read_ffmpeg_output(self) -> None:
        """Lit la sortie ffmpeg et alimente la queue audio dans une boucle asyncio."""
        loop = asyncio.get_event_loop()
        try:
            while self.is_active and self._ffmpeg_process:
                chunk = await loop.run_in_executor(
                    None, self._ffmpeg_process.stdout.read, CHUNK_SIZE
                )
                if not chunk:
                    logger.warning("Fin du flux ffmpeg détectée")
                    break

                if self._audio_queue.full():
                    try:
                        self._audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

                await self._audio_queue.put(chunk)
        except Exception as e:
            logger.error("Erreur lecture ffmpeg: %s", e)

    async def _audio_stream_generator(self):
        """Générateur asynchrone qui fournit les chunks audio à Transcribe."""
        # Attendre que la queue se remplisse un peu
        wait_count = 0
        while self._audio_queue.qsize() < 10 and self.is_active:
            await asyncio.sleep(0.1)
            wait_count += 1
            if wait_count > 100:  # 10 secondes max d'attente
                break

        empty_counter = 0
        while self.is_active:
            try:
                chunk = self._audio_queue.get_nowait()
                empty_counter = 0
                yield chunk
            except asyncio.QueueEmpty:
                empty_counter += 1
                if empty_counter > 150:  # ~15 secondes sans données
                    logger.warning("Pas de données audio depuis 15 secondes")
                    break
                await asyncio.sleep(0.1)

    async def _run_transcription(self) -> None:
        """Lance la session Transcribe Streaming et traite les résultats."""
        client = TranscribeStreamingClient(region=REGION)

        stream = await client.start_stream_transcription(
            language_code=LANGUAGE_CODE,
            media_sample_rate_hz=SAMPLE_RATE,
            media_encoding="pcm",
        )

        handler = _TranscriptHandler(stream.output_stream, self.on_message)
        handler_task = asyncio.create_task(handler.handle_events())

        async for audio_chunk in self._audio_stream_generator():
            await stream.input_stream.send_audio_event(audio_chunk=audio_chunk)

        await stream.input_stream.end_stream()
        await handler_task

    async def start(self) -> None:
        """Démarre le pipeline audio et la transcription.

        En cas d'erreur, envoie un StatusMessage d'erreur et retente
        après RECONNECT_DELAY_SECONDS secondes.
        """
        self.is_active = True
        logger.info("Démarrage de la session de transcription")

        await self.on_message(
            serialize(StatusMessage(type="status", status="transcribing", message="Transcription en cours"))
        )

        while self.is_active:
            try:
                self._start_ffmpeg()
                self._reader_task = asyncio.create_task(self._read_ffmpeg_output())
                await self._run_transcription()
            except Exception as e:
                logger.error("Erreur dans la session de transcription: %s", e)
                if self.is_active:
                    await self.on_message(
                        serialize(StatusMessage(
                            type="status",
                            status="error",
                            message=f"Erreur de transcription: {e}",
                        ))
                    )
                    logger.info("Redémarrage dans %s secondes...", RECONNECT_DELAY_SECONDS)
                    await asyncio.sleep(RECONNECT_DELAY_SECONDS)
            finally:
                self._cleanup_ffmpeg()

            if not self.is_active:
                break

    def _cleanup_ffmpeg(self) -> None:
        """Arrête proprement le processus ffmpeg."""
        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=5)
            except Exception:
                try:
                    self._ffmpeg_process.kill()
                except Exception:
                    pass
            self._ffmpeg_process = None

    async def stop(self) -> None:
        """Arrête proprement ffmpeg et la session Transcribe."""
        logger.info("Arrêt de la session de transcription")
        self.is_active = False

        self._cleanup_ffmpeg()

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Vider la queue audio
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        logger.info("Session de transcription arrêtée")
