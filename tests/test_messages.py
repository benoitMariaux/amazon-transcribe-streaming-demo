"""Tests unitaires pour messages.py — Requirements 5.1, 5.2, 5.3"""

import json
import pytest
from messages import TranscriptionMessage, StatusMessage, serialize, deserialize


class TestSerializeTranscriptionMessage:
    def test_partial_message(self):
        msg = TranscriptionMessage(type="partial", text="Bonjour", timestamp="2024-01-15T14:30:00.123Z")
        raw = serialize(msg)
        data = json.loads(raw)
        assert data == {"type": "partial", "text": "Bonjour", "timestamp": "2024-01-15T14:30:00.123Z"}

    def test_final_message(self):
        msg = TranscriptionMessage(type="final", text="Bonjour le monde", timestamp="2024-01-15T14:30:01.456Z")
        raw = serialize(msg)
        data = json.loads(raw)
        assert data == {"type": "final", "text": "Bonjour le monde", "timestamp": "2024-01-15T14:30:01.456Z"}


class TestSerializeStatusMessage:
    def test_status_message(self):
        msg = StatusMessage(type="status", status="connected", message="Connexion établie")
        raw = serialize(msg)
        data = json.loads(raw)
        assert data == {"type": "status", "status": "connected", "message": "Connexion établie"}


class TestDeserializeMissingType:
    def test_missing_type_raises_value_error(self):
        raw = json.dumps({"text": "hello", "timestamp": "2024-01-15T14:30:00Z"})
        with pytest.raises(ValueError, match="type"):
            deserialize(raw)
