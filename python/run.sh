#!/bin/bash

# Script to run real-time transcription

# Activate virtual environment
source venv/bin/activate

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg is not installed. Please install it before continuing."
    echo "On macOS: brew install ffmpeg"
    echo "On Ubuntu: sudo apt-get install ffmpeg"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo "AWS credentials not configured or invalid. Please run 'aws configure'."
    exit 1
fi

# Run the transcription script
python3 transcribe_streaming.py
