# Amazon Transcribe Real-time Streaming Demo

This project demonstrates how to use Amazon Transcribe to transcribe the audio stream from France Info radio in real-time.

## Project Structure

```
amazon-transcribe-streaming-demo/
├── transcribe_streaming.py  # Real-time streaming transcription
├── transcribe_file.py       # Batch transcription of audio file
├── audio_stream_validator.py # Validates audio stream functionality
├── run.sh                   # Script to run the streaming demo
└── requirements.txt         # Python dependencies
```

## Prerequisites

- AWS account with access to Amazon Transcribe
- ffmpeg installed on your system
- Python 3.8+

## Installation

1. Create and activate a Python virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Configure your AWS credentials:
   ```
   aws configure
   ```

## Usage

### Audio Stream Validation
To verify that downloading and converting the audio stream works correctly:
```
python audio_stream_validator.py
```

### Batch Transcription
To transcribe an audio sample with Amazon Transcribe in batch mode:
```
python transcribe_file.py
```
Results will be saved in `transcription_result.json`.

### Real-time Transcription (streaming)
To start real-time transcription:
```
python transcribe_streaming.py
```
or
```
./run.sh
```

To stop the transcription, press Ctrl+C.

## Configuration

You can modify the following parameters in the scripts:

- `STREAM_URL`: URL of the audio stream to transcribe
- `LANGUAGE_CODE`: Language code for transcription (default: fr-FR)
- `SAMPLE_RATE`: Audio sample rate (default: 16000)
- `REGION`: AWS region to use
