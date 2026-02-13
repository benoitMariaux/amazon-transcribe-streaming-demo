"""
Serveur FastAPI pour l'interface web de transcription en temps réel.

Point d'entrée de l'application : sert le frontend, expose le WebSocket
pour la diffusion des résultats de transcription, et gère le cycle de vie
(startup/shutdown) avec arrêt propre sur SIGINT/SIGTERM.
"""

import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from session_manager import SessionManager

logger = logging.getLogger(__name__)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

session_manager = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gère le cycle de vie de l'application (startup/shutdown)."""
    # Startup
    logger.info("Démarrage du serveur de transcription")
    print(f"\n  Interface web disponible sur : http://{HOST}:{PORT}\n")

    # Installer les handlers de signaux pour arrêt propre
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_handle_shutdown(s)))

    yield

    # Shutdown
    logger.info("Arrêt du serveur — fermeture des sessions")
    await session_manager.shutdown()


async def _handle_shutdown(sig: signal.Signals) -> None:
    """Gère l'arrêt propre sur réception d'un signal."""
    logger.info("Signal %s reçu — arrêt en cours", sig.name)
    await session_manager.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def get_index() -> HTMLResponse:
    """Sert la page frontend."""
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Endpoint WebSocket — délègue au SessionManager."""
    await websocket.accept()
    await session_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await session_manager.disconnect(websocket)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(app, host=HOST, port=PORT)
