#!/usr/bin/env python3
"""
Version épurée - affiche seulement le texte final sans répétition
"""

import asyncio
import subprocess
import threading
import queue
import time
from datetime import datetime

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

# Configuration
STREAM_URL = "http://icecast.radiofrance.fr/franceinfo-lofi.aac"
LANGUAGE_CODE = "fr-FR"
SAMPLE_RATE = 16000
REGION = "us-east-1"

audio_queue = queue.Queue(maxsize=100)
stop_processing = False

class CleanTranscriptHandler(TranscriptResultStreamHandler):
    """Affichage épuré des transcriptions"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_partial = ""
        
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        
        for result in results:
            for alt in result.alternatives:
                transcript = alt.transcript.strip()
                
                if result.is_partial:
                    # Mise à jour en temps réel sur la même ligne
                    if transcript and transcript != self.last_partial:
                        print(f"\r{transcript}", end="", flush=True)
                        self.last_partial = transcript
                else:
                    # Texte final : nouvelle ligne
                    if transcript:
                        print(f"\r{transcript}")
                        self.last_partial = ""

def download_and_convert_stream():
    try:
        ffmpeg_cmd = [
            'ffmpeg', '-i', STREAM_URL, '-ar', str(SAMPLE_RATE),
            '-ac', '1', '-f', 's16le', '-'
        ]
        
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**8)
        chunk_size = 1024 * 4
        
        while not stop_processing:
            audio_chunk = process.stdout.read(chunk_size)
            if not audio_chunk:
                break
                
            if audio_queue.full():
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    pass
                    
            audio_queue.put(audio_chunk)
            
        process.terminate()
        
    except Exception as e:
        print(f"Erreur: {e}")
        raise

async def audio_stream_generator():
    while audio_queue.qsize() < 10 and not stop_processing:
        await asyncio.sleep(0.1)
    
    empty_counter = 0
    while not stop_processing:
        try:
            chunk = audio_queue.get(block=True, timeout=0.1)
            empty_counter = 0
            yield chunk
        except queue.Empty:
            empty_counter += 1
            if empty_counter > 150:
                break
            await asyncio.sleep(0.01)
            continue

async def transcribe_stream():
    client = TranscribeStreamingClient(region=REGION)
    
    stream = await client.start_stream_transcription(
        language_code=LANGUAGE_CODE,
        media_sample_rate_hz=SAMPLE_RATE,
        media_encoding="pcm",
    )
    
    handler = CleanTranscriptHandler(stream.output_stream)
    await_transcription = asyncio.create_task(handler.handle_events())
    
    async for audio_chunk in audio_stream_generator():
        await stream.input_stream.send_audio_event(audio_chunk=audio_chunk)
    
    await stream.input_stream.end_stream()
    await await_transcription

def main():
    global stop_processing
    
    try:
        print("Transcription en cours... (Ctrl+C pour arrêter)\n")
        
        download_thread = threading.Thread(target=download_and_convert_stream)
        download_thread.daemon = True
        download_thread.start()
        
        time.sleep(2)
        asyncio.run(transcribe_stream())
        
    except KeyboardInterrupt:
        print("\n\nArrêt de la transcription...")
    finally:
        stop_processing = True

if __name__ == "__main__":
    main()
