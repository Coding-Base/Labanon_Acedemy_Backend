from django.contrib import admin
from .models import Video, VideoUploadSession, VideoConversionTask


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'creator', 'status', 'file_size', 'duration', 'created_at']
    list_filter = ['status', 'created_at', 'duration']
    search_fields = ['title', 'creator__email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'processed_at', 's3_original_key']
    fieldsets = (
        ('Basic Info', {'fields': ('id', 'creator', 'title', 'description')}),
        ('File Info', {'fields': ('original_file_name', 'file_size', 'duration')}),
        ('S3 References', {'fields': ('s3_original_key', 's3_hls_manifest_key', 's3_hls_folder_key')}),
        ('CloudFront', {'fields': ('cloudfront_url', 'cloudfront_thumbnail_url')}),
        ('Processing', {'fields': ('status', 'error_message')}),
        ('YouTube Fallback', {'fields': ('youtube_url',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'processed_at')}),
    )


@admin.register(VideoUploadSession)
class VideoUploadSessionAdmin(admin.ModelAdmin):
    list_display = ['video', 'upload_id', 'created_at', 'expires_at']
    list_filter = ['created_at', 'expires_at']
    search_fields = ['video__title']
    readonly_fields = ['id', 'created_at']


@admin.register(VideoConversionTask)
class VideoConversionTaskAdmin(admin.ModelAdmin):
    list_display = ['video', 'status', 'progress', 'started_at', 'completed_at']
    list_filter = ['status', 'started_at', 'completed_at']
    search_fields = ['video__title']
    readonly_fields = ['id', 'celery_task_id']
