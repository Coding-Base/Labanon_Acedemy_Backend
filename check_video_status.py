#!/usr/bin/env python
"""Test video status endpoint"""
import os
import sys
import django

sys.path.insert(0, 'c:\\Users\\USER\\Desktop\\Lebanon Acedemy\\backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import uuid
from videos.models import Video
from videos.serializers import VideoSerializer

# Get the most recently created video
try:
    video = Video.objects.latest('created_at')
    print(f"Latest video: {video.id}")
    print(f"Status: {video.status}")
    print(f"CloudFront URL: {video.cloudfront_url}")
    
    # Serialize it
    serializer = VideoSerializer(video)
    print(f"\nSerialized data:")
    print(serializer.data)
except Video.DoesNotExist:
    print("No videos found in database")
