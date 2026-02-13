from dataclasses import dataclass, asdict
import json


@dataclass
class TranscriptionMessage:
    type: str          # "partial" ou "final"
    text: str
    timestamp: str     # ISO 8601


@dataclass
class StatusMessage:
    type: str = "status"
    status: str = ""   # "connected", "transcribing", "error", "reconnecting"
    message: str = ""


def serialize(msg: TranscriptionMessage | StatusMessage) -> str:
    """Encode un message en JSON valide."""
    return json.dumps(asdict(msg))


def deserialize(raw: str) -> TranscriptionMessage | StatusMessage:
    """Décode un message JSON en objet structuré.

    Raises:
        ValueError: Si le champ 'type' est absent du JSON.
    """
    data = json.loads(raw)
    if "type" not in data:
        raise ValueError("Le champ 'type' est requis dans le message JSON")
    if data["type"] in ("partial", "final"):
        return TranscriptionMessage(**data)
    return StatusMessage(**data)
