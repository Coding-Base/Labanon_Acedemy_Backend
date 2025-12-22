from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils import timezone
import boto3
from datetime import timedelta
import uuid
import os
import requests
import logging

from .models import Video, VideoUploadSession, VideoConversionTask
from .serializers import (
    VideoSerializer, VideoUploadInitiationSerializer,
    VideoConversionTaskSerializer, PresignedUrlRequestSerializer
)
from .encoding_queue import queue_video_for_encoding

logger = logging.getLogger(__name__)


class S3Manager:
    """Handles all S3 operations for video uploads and retrieval."""
    
    def __init__(self):
        # Check if AWS is configured
        if not getattr(settings, 'USE_AWS_S3', False) or not all([
            getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None),
        ]):
            raise ValueError(
                "AWS S3 is not properly configured. "
                "Please set USE_AWS_S3=True and provide AWS credentials in .env file"
            )
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1'),
            config=boto3.session.Config(signature_version='s3v4')
        )
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self.cloudfront_domain = getattr(settings, 'CLOUDFRONT_DOMAIN', None)
    
    def initiate_multipart_upload(self, video_id: str, file_name: str) -> str:
        """Initiate multipart upload and return upload ID."""
        key = f"videos/{video_id}/original/{file_name}"
        response = self.s3_client.create_multipart_upload(
            Bucket=self.bucket_name,
            Key=key,
            ContentType='video/mp4',
            Metadata={'video_id': str(video_id)}
        )
        return response['UploadId'], key
    
    def get_presigned_upload_url(self, bucket: str, key: str, part_number: int, upload_id: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for uploading a part."""
        return self.s3_client.generate_presigned_url(
            'upload_part',
            Params={
                'Bucket': bucket,
                'Key': key,
                'PartNumber': part_number,
                'UploadId': upload_id
            },
            ExpiresIn=expires_in
        )
    
    def complete_multipart_upload(self, bucket: str, key: str, upload_id: str, parts: list) -> dict:
        """Complete multipart upload."""
        response = self.s3_client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )
        return response
    
    def abort_multipart_upload(self, bucket: str, key: str, upload_id: str):
        """Abort incomplete multipart upload."""
        self.s3_client.abort_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id
        )
    
    def generate_hls_manifest_url(self, video_id: str) -> str:
        """Generate CloudFront URL for HLS manifest."""
        manifest_key = f"videos/{video_id}/hls/manifest.m3u8"
        return f"https://{self.cloudfront_domain}/{manifest_key}"
    
    def generate_thumbnail_url(self, video_id: str) -> str:
        """Generate CloudFront URL for thumbnail."""
        thumbnail_key = f"videos/{video_id}/thumbnail.jpg"
        return f"https://{self.cloudfront_domain}/{thumbnail_key}"


class VideoViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling video uploads, processing, and retrieval.
    Supports resumable multipart uploads with S3.
    """
    serializer_class = VideoSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        """Return videos for the current user."""
        return Video.objects.filter(creator=self.request.user)
    
    @action(detail=False, methods=['post'])
    def initiate_upload(self, request):
        """
        Initiate video upload session.
        Returns upload ID, video ID, and presigned URL for first part.
        """
        serializer = VideoUploadInitiationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        video_id = uuid.uuid4()
        
        # Create Video object
        video = Video.objects.create(
            id=video_id,
            creator=request.user,
            title=data['title'],
            description=data.get('description', ''),
            original_file_name=data['file_name'],
            file_size=data['file_size'],
            duration=data.get('duration'),
            s3_original_key='',  # Will be set during completion
            status='uploading'
        )
        
        # Initiate S3 multipart upload
        s3_manager = S3Manager()
        try:
            upload_id, s3_key = s3_manager.initiate_multipart_upload(
                str(video_id),
                data['file_name']
            )
            
            video.s3_original_key = s3_key
            video.save()
            
            # Create upload session
            VideoUploadSession.objects.create(
                video=video,
                upload_id=upload_id,
                expires_at=timezone.now() + timedelta(hours=24)
            )
            
            # Get presigned URL for first part
            presigned_url = s3_manager.get_presigned_upload_url(
                s3_manager.bucket_name,
                s3_key,
                1,
                upload_id
            )
            
            return Response({
                'video_id': str(video_id),
                'upload_id': upload_id,
                's3_key': s3_key,
                'presigned_url': presigned_url,
                'part_number': 1
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            video.delete()
            return Response(
                {'error': f'Failed to initiate upload: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def get_presigned_url(self, request):
        """Get presigned URL for uploading a part."""
        serializer = PresignedUrlRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        video_id = serializer.validated_data['video_id']
        part_number = serializer.validated_data['part_number']
        
        try:
            video = Video.objects.get(id=video_id, creator=request.user)
            session = video.upload_session
            
            s3_manager = S3Manager()
            presigned_url = s3_manager.get_presigned_upload_url(
                s3_manager.bucket_name,
                video.s3_original_key,
                part_number,
                session.upload_id
            )
            
            return Response({
                'presigned_url': presigned_url,
                'part_number': part_number
            })
        
        except Video.DoesNotExist:
            return Response(
                {'error': 'Video not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['post'])
    def complete_upload(self, request):
        """
        Complete multipart upload.
        Queues video to EncodingBackend via Redis for HLS conversion.
        
        Request:
            {
                'video_id': 'uuid',
                'parts': [{'PartNumber': 1, 'ETag': 'etag'}, ...]
            }
        
        Response:
            {
                'message': 'Upload completed successfully',
                'video_id': 'uuid',
                'status': 'queued_for_encoding'
            }
        """
        video_id = request.data.get('video_id')
        parts = request.data.get('parts', [])
        
        if not video_id or not parts:
            return Response(
                {'error': 'Missing video_id or parts'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            video = Video.objects.get(id=video_id, creator=request.user)
            session = video.upload_session
            
            s3_manager = S3Manager()
            result = s3_manager.complete_multipart_upload(
                s3_manager.bucket_name,
                video.s3_original_key,
                session.upload_id,
                parts
            )
            
            # Update video status to queued for encoding
            video.status = 'queued_for_encoding'
            video.save()
            
            # Queue to EncodingBackend via Redis
            quality_presets = request.data.get('quality_presets', ['720p', '480p', '360p'])
            queue_success = queue_video_for_encoding(
                video_id=str(video.id),
                s3_original_key=video.s3_original_key,
                duration=video.duration or 0,
                file_size=video.file_size,
                quality_presets=quality_presets
            )
            
            if not queue_success:
                logger.warning(f"Failed to queue video {video.id} for encoding, but upload was successful")
            
            return Response({
                'message': 'Upload completed successfully',
                'video_id': str(video.id),
                'status': video.status,
                's3_key': result['Key'],
                'note': 'Video queued for encoding in EncodingBackend service'
            })
        
        except Video.DoesNotExist:
            return Response(
                {'error': 'Video not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error completing upload: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail='id', methods=['get'])
    def conversion_status(self, request, id=None):
        """Get conversion task status for a video."""
        try:
            video = Video.objects.get(id=id, creator=request.user)
            try:
                task = video.conversion_task
                serializer = VideoConversionTaskSerializer(task)
                return Response(serializer.data)
            except VideoConversionTask.DoesNotExist:
                return Response({'status': 'no_task'})
        except Video.DoesNotExist:
            return Response(
                {'error': 'Video not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail='id', methods=['post'])
    def update_encoding_status(self, request, id=None):
        """
        Update video encoding status (called by EncodingBackend service)
        
        Request:
            {
                'status': 'ready' | 'failed',
                'error_message': '...' (optional, only if failed)
            }
        """
        try:
            video = Video.objects.get(id=id)
            
            new_status = request.data.get('status', 'ready')
            error_message = request.data.get('error_message', '')
            
            # Update video status
            video.status = new_status
            if error_message:
                video.error_message = error_message
            video.save()
            
            logger.info(f"Video {id} encoding status updated to {new_status}")
            
            return Response({
                'message': f'Video status updated to {new_status}',
                'video_id': str(video.id),
                'status': video.status
            })
        
        except Video.DoesNotExist:
            return Response(
                {'error': 'Video not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error updating video status: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Get video details."""
        response = super().retrieve(request, *args, **kwargs)
        return response
    
    def list(self, request, *args, **kwargs):
        """List user's videos."""
        response = super().list(request, *args, **kwargs)
        return response
