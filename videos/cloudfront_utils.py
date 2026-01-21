"""
CloudFront Signed URL generation for secure video access.
Ensures videos can only be accessed with a valid, time-limited token.
Includes custom header generation for additional security layers.
"""
import os
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from botocore.signers import CloudFrontSigner
from django.conf import settings


class CloudFrontURLSigner:
    """Generate CloudFront Signed URLs for secure video access."""
    
    def __init__(self):
        self.cloudfront_domain = getattr(settings, 'CLOUDFRONT_DOMAIN', None)
        self.cloudfront_key_pair_id = getattr(settings, 'CLOUDFRONT_KEY_PAIR_ID', None)
        self.cloudfront_private_key_path = getattr(settings, 'CLOUDFRONT_PRIVATE_KEY_PATH', None)
        self.cloudfront_custom_auth_secret = getattr(settings, 'CLOUDFRONT_CUSTOM_AUTH_SECRET', '')
        
        if not all([self.cloudfront_domain, self.cloudfront_key_pair_id, self.cloudfront_private_key_path]):
            raise ValueError(
                "CloudFront signing is not properly configured. "
                "Please set CLOUDFRONT_DOMAIN, CLOUDFRONT_KEY_PAIR_ID, and CLOUDFRONT_PRIVATE_KEY_PATH in .env"
            )
        
        # Load and validate private key
        if not os.path.exists(self.cloudfront_private_key_path):
            raise ValueError(
                f"CloudFront private key not found at {self.cloudfront_private_key_path}. "
                f"Ensure CLOUDFRONT_PRIVATE_KEY_CONTENT or CLOUDFRONT_PRIVATE_KEY_PATH is set correctly in .env"
            )
        
        try:
            with open(self.cloudfront_private_key_path, 'rb') as f:
                key_content = f.read()
                
                if not key_content.startswith(b'-----BEGIN'):
                    raise ValueError(
                        f"Invalid PEM file format: does not start with '-----BEGIN'. "
                        f"This usually means escaped newlines in environment variable. "
                        f"Ensure CLOUDFRONT_PRIVATE_KEY_CONTENT uses proper newlines, not \\n"
                    )
                
                self.private_key = key_content
        except Exception as e:
            raise ValueError(
                f"Failed to validate CloudFront private key: {str(e)}"
            )
    
    def generate_signed_url(self, path: str, expires_in_hours: int = 24) -> str:
        """
        Generate a signed CloudFront URL.
        
        Args:
            path: CloudFront path (e.g., /videos/123/hls/master.m3u8)
            expires_in_hours: URL expiration time in hours (default: 24)
        
        Returns:
            Complete signed CloudFront URL
        """
        url = f"https://{self.cloudfront_domain}{path}"
        
        # Create signer with private key
        signer = CloudFrontSigner(self.cloudfront_key_pair_id, self._rsa_signer)
        
        # Expiration time
        expires = datetime.utcnow() + timedelta(hours=expires_in_hours)
        
        # Generate signed URL
        signed_url = signer.generate_presigned_url(
            url,
            date_less_than=expires
        )
        
        return signed_url
    
    def _rsa_signer(self, message):
        """Sign message with RSA private key."""
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        
        private_key = self._load_private_key()
        return private_key.sign(
            message,
            padding.PKCS1v15(),
            hashes.SHA1()
        )
    
    def _load_private_key(self):
        """Load RSA private key from file."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        try:
            with open(self.cloudfront_private_key_path, 'rb') as f:
                key_content = f.read()
                
                # Debug: Check if key looks valid
                if not key_content.startswith(b'-----BEGIN'):
                    raise ValueError(
                        f"Invalid PEM file format: does not start with '-----BEGIN'. "
                        f"First 100 bytes: {key_content[:100]}"
                    )
                
                private_key = serialization.load_pem_private_key(
                    key_content,
                    password=None,
                    backend=default_backend()
                )
            return private_key
        except Exception as e:
            raise ValueError(
                f"Failed to load CloudFront private key from {self.cloudfront_private_key_path}: {str(e)}"
            )
    
    def generate_hls_signed_url(self, video_id: str, expires_in_hours: int = 24) -> str:
        """
        Generate signed URL for HLS master manifest.
        
        Args:
            video_id: Video UUID
            expires_in_hours: URL expiration time in hours
        
        Returns:
            Signed CloudFront URL for the HLS manifest
        """
        manifest_path = f"/videos/{video_id}/hls/master.m3u8"
        return self.generate_signed_url(manifest_path, expires_in_hours)
    
    def generate_thumbnail_signed_url(self, video_id: str, expires_in_hours: int = 168) -> str:
        """
        Generate signed URL for video thumbnail.
        
        Args:
            video_id: Video UUID
            expires_in_hours: URL expiration time in hours (default: 7 days)
        
        Returns:
            Signed CloudFront URL for the thumbnail
        """
        thumbnail_path = f"/videos/{video_id}/thumbnail.jpg"
        return self.generate_signed_url(thumbnail_path, expires_in_hours)
    
    def generate_auth_header(self, user_id: int | str, video_id: str) -> str:
        """
        Generate custom authentication header value for frontend.
        
        Creates an HMAC-SHA256 signature combining user_id and video_id.
        Frontend includes this header with video requests for additional verification.
        
        Args:
            user_id: User ID (int or str)
            video_id: Video UUID
        
        Returns:
            Auth header value in format: "{user_id}:{video_id}:{timestamp}:{signature}"
        """
        if not self.cloudfront_custom_auth_secret:
            return ''
        
        timestamp = str(int(time.time()))
        message = f"{user_id}:{video_id}:{timestamp}"
        
        signature = hmac.new(
            self.cloudfront_custom_auth_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"{message}:{signature}"
