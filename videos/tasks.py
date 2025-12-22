# from celery import shared_task
# from django.conf import settings
# import boto3
# import subprocess
# import os
# import tempfile
# from pathlib import Path
# from datetime import datetime
# from .models import Video, VideoConversionTask
#
#
# @shared_task(bind=True)
# def convert_video_to_hls(self, video_id):
#     """
#     Convert video to HLS format and upload segments to S3.
#     This task is called after video upload is complete.
#     """
#     try:
#         video = Video.objects.get(id=video_id)
#         conversion_task = VideoConversionTask.objects.get(video=video)
#         conversion_task.celery_task_id = self.request.id
#         conversion_task.status = 'processing'
#         conversion_task.started_at = datetime.now()
#         conversion_task.save()
#         
#         # Initialize S3 client
#         s3_client = boto3.client(
#             's3',
#             aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#             aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#             region_name=settings.AWS_S3_REGION_NAME
#         )
#         
#         # Create temp directory for processing
#         with tempfile.TemporaryDirectory() as temp_dir:
#             temp_path = Path(temp_dir)
#             
#             # Download original video from S3
#             original_path = temp_path / 'original.mp4'
#             s3_client.download_file(
#                 settings.AWS_STORAGE_BUCKET_NAME,
#                 video.s3_original_key,
#                 str(original_path)
#             )
#             
#             # Create output directory for HLS segments
#             hls_output_dir = temp_path / 'hls'
#             hls_output_dir.mkdir()
#             
#             # Convert to HLS using ffmpeg
#             manifest_path = hls_output_dir / 'manifest.m3u8'
#             segment_pattern = hls_output_dir / 'segment%03d.ts'
#             
#             cmd = [
#                 'ffmpeg',
#                 '-i', str(original_path),
#                 '-c:v', 'libx264',  # Video codec
#                 '-c:a', 'aac',  # Audio codec
#                 '-b:v', '2500k',  # Video bitrate
#                 '-b:a', '128k',  # Audio bitrate
#                 '-hls_time', '10',  # Segment duration (10 seconds)
#                 '-hls_list_size', '0',  # Include all segments in manifest
#                 '-f', 'hls',
#                 str(manifest_path)
#             ]
#             
#             result = subprocess.run(cmd, capture_output=True, text=True)
#             if result.returncode != 0:
#                 raise Exception(f"FFmpeg error: {result.stderr}")
#             
#             # Upload HLS segments to S3
#             hls_folder_key = f"videos/{video_id}/hls"
#             
#             for file in hls_output_dir.iterdir():
#                 if file.is_file():
#                     s3_key = f"{hls_folder_key}/{file.name}"
#                     s3_client.upload_file(str(file), settings.AWS_STORAGE_BUCKET_NAME, s3_key)
#             
#             # Generate and upload thumbnail
#             thumbnail_path = temp_path / 'thumbnail.jpg'
#             cmd_thumbnail = [
#                 'ffmpeg',
#                 '-i', str(original_path),
#                 '-ss', '00:00:05',
#                 '-vframes', '1',
#                 '-vf', 'scale=320:-1',
#                 str(thumbnail_path)
#             ]
#             subprocess.run(cmd_thumbnail, capture_output=True)
#             
#             if thumbnail_path.exists():
#                 thumbnail_key = f"videos/{video_id}/thumbnail.jpg"
#                 s3_client.upload_file(str(thumbnail_path), settings.AWS_STORAGE_BUCKET_NAME, thumbnail_key)
#                 video.cloudfront_thumbnail_url = f"https://{settings.CLOUDFRONT_DOMAIN}/{thumbnail_key}"
#         
#         # Update video record
#         video.s3_hls_manifest_key = f"{hls_folder_key}/manifest.m3u8"
#         video.s3_hls_folder_key = hls_folder_key
#         video.cloudfront_url = f"https://{settings.CLOUDFRONT_DOMAIN}/{video.s3_hls_manifest_key}"
#         video.status = 'ready'
#         video.processed_at = datetime.now()
#         video.save()
#         
#         # Update conversion task
#         conversion_task.status = 'completed'
#         conversion_task.progress = 100
#         conversion_task.completed_at = datetime.now()
#         conversion_task.save()
#         
#         # Delete original file from S3 to save storage
#         # Uncomment if you want to delete original after successful conversion
#         # s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=video.s3_original_key)
#         
#         return {'status': 'success', 'video_id': str(video_id)}
#     
#     except Exception as exc:
#         conversion_task = VideoConversionTask.objects.get(video__id=video_id)
#         conversion_task.status = 'failed'
#         conversion_task.error_message = str(exc)
#         conversion_task.save()
#         
#         video = Video.objects.get(id=video_id)
#         video.status = 'failed'
#         video.error_message = str(exc)
#         video.save()
#         
#         return {'status': 'failed', 'error': str(exc)}
