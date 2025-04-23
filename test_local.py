#!/usr/bin/env python3
"""
Local test to verify that downloading and converting the audio stream works correctly
"""

import subprocess
import os
import time
import tempfile

# Configuration
STREAM_URL = "http://icecast.radiofrance.fr/franceinfo-lofi.aac"
SAMPLE_RATE = 16000
OUTPUT_FILE = "test_audio.wav"
DURATION = 10  # Recording duration in seconds

def test_stream_download():
    """Tests downloading and converting the audio stream"""
    print(f"Testing stream download: {STREAM_URL}")
    print(f"Recording {DURATION} seconds...")
    
    try:
        # Use ffmpeg to download and convert the stream
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', STREAM_URL,
            '-t', str(DURATION),
            '-ar', str(SAMPLE_RATE),
            '-ac', '1',
            '-y',  # Overwrite file if it exists
            OUTPUT_FILE
        ]
        
        # Execute the command
        process = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Check if the command succeeded
        if process.returncode == 0:
            file_size = os.path.getsize(OUTPUT_FILE)
            print(f"Success! File created: {OUTPUT_FILE} ({file_size} bytes)")
            print(f"You can listen to the file to verify the quality.")
            return True
        else:
            print(f"Error executing ffmpeg: {process.stderr}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_stream_to_pcm():
    """Tests converting the stream to PCM for Transcribe"""
    print(f"Testing stream conversion to PCM...")
    
    try:
        # Create a temporary file to store a PCM sample
        with tempfile.NamedTemporaryFile(suffix='.pcm', delete=False) as temp_file:
            temp_filename = temp_file.name
        
        # Use ffmpeg to convert the stream to PCM
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', STREAM_URL,
            '-t', str(DURATION),
            '-ar', str(SAMPLE_RATE),
            '-ac', '1',
            '-f', 's16le',  # 16-bit little-endian PCM format
            '-y',
            temp_filename
        ]
        
        # Execute the command
        process = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Check if the command succeeded
        if process.returncode == 0:
            file_size = os.path.getsize(temp_filename)
            print(f"Success! PCM file created: {temp_filename} ({file_size} bytes)")
            
            # Convert PCM to WAV for listening
            wav_filename = temp_filename + ".wav"
            ffmpeg_cmd = [
                'ffmpeg',
                '-f', 's16le',
                '-ar', str(SAMPLE_RATE),
                '-ac', '1',
                '-i', temp_filename,
                '-y',
                wav_filename
            ]
            
            subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"WAV file created for listening: {wav_filename}")
            
            # Clean up the PCM file
            os.unlink(temp_filename)
            return True
        else:
            print(f"Error executing ffmpeg: {process.stderr}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("=== Testing audio stream download ===")
    success1 = test_stream_download()
    
    print("\n=== Testing conversion to PCM for Transcribe ===")
    success2 = test_stream_to_pcm()
    
    if success1 and success2:
        print("\n✅ All tests passed! The audio stream can be used with Transcribe.")
    else:
        print("\n❌ Some tests failed. Check the errors above.")
