#!/usr/bin/env python3
"""
Test transcription of a local audio file with Amazon Transcribe
"""

import sys
import time
import json
import os
import boto3
import uuid

# Configuration
LANGUAGE_CODE = "fr-FR"  # French
REGION = "eu-west-1"  # Change according to your AWS region
INPUT_FILE = "test_audio.wav"  # File created by test_local.py
OUTPUT_FILE = "transcription_result.json"

def transcribe_file():
    """Transcribes a local audio file with Amazon Transcribe (batch mode)"""
    
    # Check that the file exists
    if not os.path.exists(INPUT_FILE):
        print(f"Error: File {INPUT_FILE} does not exist.")
        print("Run test_local.py first to create a test audio file.")
        return False
    
    # Create a Transcribe client
    transcribe = boto3.client('transcribe', region_name=REGION)
    
    # Unique name for the transcription job
    job_name = f"test-transcription-{uuid.uuid4()}"
    
    # Absolute path to the audio file
    file_path = os.path.abspath(INPUT_FILE)
    
    try:
        # Create an S3 client
        s3 = boto3.client('s3', region_name=REGION)
        
        # Create a temporary bucket for the audio file
        bucket_name = f"transcribe-test-{uuid.uuid4().hex}"
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )
        print(f"S3 bucket created: {bucket_name}")
        
        # Upload the audio file to S3
        s3_key = os.path.basename(file_path)
        s3.upload_file(file_path, bucket_name, s3_key)
        print(f"Audio file uploaded to S3: s3://{bucket_name}/{s3_key}")
        
        # Start the transcription job
        s3_uri = f"s3://{bucket_name}/{s3_key}"
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            LanguageCode=LANGUAGE_CODE,
            MediaFormat=os.path.splitext(INPUT_FILE)[1][1:],  # Format based on extension
            Media={'MediaFileUri': s3_uri},
            Settings={
                'ShowSpeakerLabels': False,
                'ShowAlternatives': False
            }
        )
        print(f"Transcription job started: {job_name}")
        
        # Wait for the job to complete
        while True:
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            job_status = status['TranscriptionJob']['TranscriptionJobStatus']
            
            if job_status in ['COMPLETED', 'FAILED']:
                break
                
            print(f"Job status: {job_status}. Waiting...")
            time.sleep(5)
        
        # Check if the job succeeded
        if job_status == 'COMPLETED':
            # Get the result URL
            transcript_url = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
            
            # Download the result
            import requests
            response = requests.get(transcript_url)
            transcript_data = response.json()
            
            # Save the result to a file
            with open(OUTPUT_FILE, 'w') as f:
                json.dump(transcript_data, f, indent=2)
                
            # Display the transcription
            transcript = transcript_data['results']['transcripts'][0]['transcript']
            print("\nTranscription successful:")
            print("-" * 50)
            print(transcript)
            print("-" * 50)
            print(f"Complete result saved to: {OUTPUT_FILE}")
            
            # Clean up S3 resources
            s3.delete_object(Bucket=bucket_name, Key=s3_key)
            s3.delete_bucket(Bucket=bucket_name)
            print(f"S3 resources cleaned up")
            
            return True
        else:
            error = status['TranscriptionJob'].get('FailureReason', 'Unknown reason')
            print(f"Transcription job failed: {error}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("=== Testing transcription with Amazon Transcribe (batch mode) ===")
    success = transcribe_file()
    
    if success:
        print("\n✅ Transcription test successful!")
    else:
        print("\n❌ Transcription test failed. Check the errors above.")
