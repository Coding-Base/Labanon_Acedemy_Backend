from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
import uuid


class Video(models.Model):
    """
    Main video model for storing video metadata and S3 references.
    Videos are converted to HLS format and served via CloudFront.
    """
    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('queued_for_encoding', 'Queued for Encoding'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='videos')
    
    # Original file info
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    original_file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()  # bytes
    duration = models.FloatField(null=True, blank=True)  # seconds
    
    # S3 references
    s3_original_key = models.CharField(max_length=512)  # Path to original file in S3
    s3_hls_manifest_key = models.CharField(max_length=512, blank=True)  # Path to HLS manifest (.m3u8)
    s3_hls_folder_key = models.CharField(max_length=512, blank=True)  # Folder containing HLS segments
    
    # CloudFront references
    cloudfront_url = models.URLField(blank=True, null=True)  # CDN URL to HLS manifest
    cloudfront_thumbnail_url = models.URLField(blank=True, null=True)  # CDN URL to thumbnail
    
    # Processing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploading')
    error_message = models.TextField(blank=True, null=True)
    
    # YouTube fallback
    youtube_url = models.URLField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.status})"


class VideoUploadSession(models.Model):
    """
    Tracks multipart upload sessions and provides resumable upload capability.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name='upload_session')
    upload_id = models.CharField(max_length=255)  # S3 multipart upload ID
    parts_uploaded = models.JSONField(default=dict)  # { "1": "etag1", "2": "etag2" }
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # Cleanup expired sessions
    
    def __str__(self):
        return f"Upload session for {self.video.title}"


class VideoConversionTask(models.Model):
    """
    Tracks video conversion progress (conversion to HLS format).
    """
    QUEUE_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name='conversion_task')
    celery_task_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=QUEUE_STATUS, default='pending')
    progress = models.IntegerField(default=0)  # 0-100
    error_message = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Conversion task for {self.video.title}"
