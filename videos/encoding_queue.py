"""
Redis Queue Manager for Main Backend
Publishes encoding jobs to Redis queue for EncodingBackend to consume
"""

import json
import redis
import os
import uuid
from django.conf import settings

# Initialize Redis connection for encoding queue (DB 1)
# Prefer REDIS_URL (set by Dokploy). Fall back to REDIS_HOST/PORT if needed.
redis_url = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL')
if redis_url:
    try:
        # Use DB 1 for encoding queue regardless of provided URL
        redis_client = redis.from_url(redis_url, db=1, decode_responses=True)
    except Exception:
        # Fallback to simple Redis client if parsing fails
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD', None)
        redis_client = redis.Redis(host=redis_host, port=redis_port, db=1, password=redis_password, decode_responses=True)
else:
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', 6379))
    redis_password = os.getenv('REDIS_PASSWORD', None)
    redis_client = redis.Redis(host=redis_host, port=redis_port, db=1, password=redis_password, decode_responses=True)

# Encoding queue name
ENCODING_QUEUE = 'video_encoding_queue'


def queue_video_for_encoding(video_id, s3_original_key, duration, file_size, quality_presets=None):
    """
    Queue a video for encoding by EncodingBackend
    
    Args:
        video_id: UUID of the video
        s3_original_key: S3 path to original video
        duration: Video duration in seconds
        file_size: File size in bytes
        quality_presets: List of quality levels ['720p', '480p', '360p']
    
    Returns:
        bool: True if queued successfully
    """
    if quality_presets is None:
        quality_presets = ['720p', '480p', '360p']
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Calculate HLS folder key
    s3_hls_folder_key = f"videos/{video_id}/hls"
    
    job_data = {
        'job_id': job_id,
        'video_id': str(video_id),
        's3_original_key': s3_original_key,
        's3_hls_folder_key': s3_hls_folder_key,
        'input_file_size': file_size,
        'duration': duration,
        'quality_presets': quality_presets,
    }
    
    try:
        # Publish to encoding queue
        redis_client.rpush(ENCODING_QUEUE, json.dumps(job_data))
        print(f"✓ Video {video_id} queued for encoding with job_id {job_id}")
        return True
    except Exception as e:
        print(f"✗ Error queueing video {video_id}: {str(e)}")
        return False


def test_redis_connection():
    """Test Redis connection for encoding queue"""
    try:
        redis_client.ping()
        print("✓ Redis connection successful")
        return True
    except Exception as e:
        print(f"✗ Redis connection failed: {str(e)}")
        return False


def get_queue_stats():
    """Get encoding queue statistics"""
    try:
        queue_length = redis_client.llen(ENCODING_QUEUE)
        return {
            'pending_videos': queue_length,
        }
    except Exception as e:
        return {
            'error': str(e),
        }
