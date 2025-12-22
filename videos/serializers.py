from rest_framework import serializers
from .models import Video, VideoUploadSession, VideoConversionTask


class VideoUploadInitiationSerializer(serializers.Serializer):
    """Serializer for initiating video upload."""
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    file_name = serializers.CharField(max_length=255)
    file_size = serializers.IntegerField()  # bytes
    file_type = serializers.CharField()  # e.g., "video/mp4"
    duration = serializers.FloatField(required=False)  # seconds, from frontend


class VideoSerializer(serializers.ModelSerializer):
    """Serializer for Video model."""
    creator_name = serializers.CharField(source='creator.get_full_name', read_only=True)
    
    class Meta:
        model = Video
        fields = [
            'id', 'creator', 'creator_name', 'title', 'description',
            'original_file_name', 'file_size', 'duration', 's3_original_key',
            's3_hls_manifest_key', 's3_hls_folder_key', 'cloudfront_url',
            'cloudfront_thumbnail_url', 'status', 'error_message', 'youtube_url',
            'created_at', 'updated_at', 'processed_at'
        ]
        read_only_fields = [
            'id', 'creator', 'creator_name', 's3_original_key', 's3_hls_manifest_key',
            's3_hls_folder_key', 'cloudfront_url', 'cloudfront_thumbnail_url',
            'status', 'error_message', 'created_at', 'updated_at', 'processed_at'
        ]


class VideoConversionTaskSerializer(serializers.ModelSerializer):
    video_id = serializers.CharField(source='video.id', read_only=True)
    video_title = serializers.CharField(source='video.title', read_only=True)
    
    class Meta:
        model = VideoConversionTask
        fields = [
            'id', 'video_id', 'video_title', 'celery_task_id', 'status',
            'progress', 'error_message', 'started_at', 'completed_at'
        ]
        read_only_fields = fields


class PresignedUrlRequestSerializer(serializers.Serializer):
    """Serializer for requesting presigned URLs for multipart upload."""
    video_id = serializers.CharField()
    part_number = serializers.IntegerField()
    content_length = serializers.IntegerField()
