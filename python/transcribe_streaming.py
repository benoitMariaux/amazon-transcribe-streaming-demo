#!/usr/bin/env python3
"""
Real-time transcription of an HTTP stream (France Info) with Amazon Transcribe Streaming
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
LANGUAGE_CODE = "fr-FR"  # French
SAMPLE_RATE = 16000  # 16 kHz
REGION = "eu-west-1"  # Change according to your AWS region

# Queue to store audio segments for transcription
audio_queue = queue.Queue(maxsize=100)  # Limit queue size
# Flag to indicate when to stop processing
stop_processing = False

class TranscriptHandler(TranscriptResultStreamHandler):
    """Handles real-time transcription results"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.results = []
        
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        """Processes each transcription event"""
        results = transcript_event.transcript.results
        
        for result in results:
            for alt in result.alternatives:
                transcript = alt.transcript
                
                # Display result with timestamp
                timestamp = datetime.now().strftime("%H:%M:%S")
                if result.is_partial:
                    print(f"[{timestamp}] [PARTIAL] {transcript}")
                else:
                    print(f"[{timestamp}] [FINAL] {transcript}")
                    
                    # Store the final result
                    self.results.append({
                        "timestamp": timestamp,
                        "transcript": transcript
                    })

def download_and_convert_stream():
    """Downloads the audio stream and converts it to a format compatible with Transcribe"""
    print("Starting download and conversion of audio stream...")
    
    try:
        # Use ffmpeg to convert AAC stream to 16kHz mono PCM
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', STREAM_URL,
            '-ar', str(SAMPLE_RATE),
            '-ac', '1',
            '-f', 's16le',
            '-'
        ]
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8  # Large buffer to avoid blocking
        )
        
        # Read audio data in blocks and put them in the queue
        chunk_size = 1024 * 4  # 4KB chunks (smaller for smoother streaming)
        chunks_read = 0
        
        while not stop_processing:
            audio_chunk = process.stdout.read(chunk_size)
            if not audio_chunk:
                print("End of audio stream detected")
                break
                
            # If the queue is full, remove an old item
            if audio_queue.full():
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    pass
                    
            audio_queue.put(audio_chunk)
            chunks_read += 1
            
            if chunks_read % 100 == 0:  # Log every 100 chunks
                print(f"Chunks read: {chunks_read}, Queue size: {audio_queue.qsize()}")
            
        process.terminate()
        print("Audio stream conversion completed")
        
    except Exception as e:
        print(f"Error during stream download/conversion: {e}")
        raise

async def audio_stream_generator():
    """Generator that provides audio chunks to Transcribe"""
    print("Starting audio stream generator...")
    
    # Wait for the queue to start filling
    while audio_queue.qsize() < 10 and not stop_processing:
        await asyncio.sleep(0.1)
    
    print(f"Queue filled with {audio_queue.qsize()} chunks, starting transcription...")
    
    # Send audio chunks to Transcribe
    empty_counter = 0
    while not stop_processing:
        try:
            # Get an audio chunk from the queue with a short timeout
            chunk = audio_queue.get(block=True, timeout=0.1)
            empty_counter = 0
            yield chunk
        except queue.Empty:
            empty_counter += 1
            if empty_counter > 150:  # 15 seconds without data (150 * 0.1s)
                print("No audio data received for 15 seconds, stopping streaming")
                break
            await asyncio.sleep(0.01)
            continue
        except Exception as e:
            print(f"Error in audio generator: {e}")
            break

async def transcribe_stream():
    """Starts transcription of the audio stream"""
    # Create Transcribe Streaming client
    client = TranscribeStreamingClient(region=REGION)
    
    # Start transcription
    stream = await client.start_stream_transcription(
        language_code=LANGUAGE_CODE,
        media_sample_rate_hz=SAMPLE_RATE,
        media_encoding="pcm",
    )
    
    # Create and associate the transcription handler
    handler = TranscriptHandler(stream.output_stream)
    
    # Start processing transcription results in another task
    await_transcription = asyncio.create_task(handler.handle_events())
    
    # Send audio data to the transcription service
    async for audio_chunk in audio_stream_generator():
        await stream.input_stream.send_audio_event(audio_chunk=audio_chunk)
    
    # Signal the end of the audio stream
    await stream.input_stream.end_stream()
    
    # Wait for transcription to complete
    await await_transcription

async def main_async():
    """Main asynchronous function"""
    try:
        # Start transcription
        await transcribe_stream()
    except Exception as e:
        print(f"Error in transcription: {e}")

def main():
    """Main function"""
    global stop_processing
    
    try:
        print("Starting real-time transcription of France Info...")
        
        # Start the download and conversion thread
        download_thread = threading.Thread(target=download_and_convert_stream)
        download_thread.daemon = True
        download_thread.start()
        
        # Wait a bit for the queue to start filling
        time.sleep(2)
        
        # Run transcription
        asyncio.run(main_async())
        
    except KeyboardInterrupt:
        print("\nInterruption detected, shutting down...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Clean up resources
        stop_processing = True
        if 'download_thread' in locals() and download_thread.is_alive():
            download_thread.join(timeout=2)
        print("Transcription completed")

if __name__ == "__main__":
    main()
