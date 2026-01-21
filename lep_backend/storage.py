"""
Custom storage backends for different media types.
- Cloudinary: Used for images, documents, and general media
- AWS S3: Used exclusively for videos
"""

import os
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class CloudinaryStorage:
    """Storage backend for Cloudinary media (images, documents, etc.)"""
    pass


class VideoS3Storage(S3Boto3Storage):
    """Storage backend specifically for videos on AWS S3"""
    def __init__(self):
        super().__init__()
        self.default_acl = 'private'  # Videos should be private/signed
        self.file_overwrite = False
        

def get_cloudinary_storage():
    """Get Cloudinary storage if USE_CLOUDINARY is enabled"""
    use_cloudinary = os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes')
    
    if use_cloudinary:
        try:
            from cloudinary_storage.storage import MediaCloudinaryStorage
            return MediaCloudinaryStorage()
        except ImportError:
            return None
    return None


def get_s3_storage():
    """Get S3 storage if USE_AWS_S3 is enabled"""
    use_aws_s3 = os.environ.get('USE_AWS_S3', 'False').lower() in ('1', 'true', 'yes')
    
    if use_aws_s3:
        return VideoS3Storage()
    return None
