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
        self.cloudfront_private_key_content = getattr(settings, 'CLOUDFRONT_PRIVATE_KEY_CONTENT', None) or os.environ.get('CLOUDFRONT_PRIVATE_KEY_CONTENT', '')
        self.cloudfront_custom_auth_secret = getattr(settings, 'CLOUDFRONT_CUSTOM_AUTH_SECRET', '')
        
        if not all([self.cloudfront_domain, self.cloudfront_key_pair_id]):
            raise ValueError(
                "CloudFront signing is not properly configured. "
                "Please set CLOUDFRONT_DOMAIN and CLOUDFRONT_KEY_PAIR_ID in .env"
            )
        
        # Load and validate private key from either file or environment variable
        key_content = None
        key_source = None
        
        # Try to load from environment variable first (for deployed environments)
        if self.cloudfront_private_key_content:
            key_content = self.cloudfront_private_key_content
            key_source = "CLOUDFRONT_PRIVATE_KEY_CONTENT environment variable"
            # Handle escaped newlines
            if '\\n' in key_content and not '\n' in key_content:
                key_content = key_content.replace('\\n', '\n')
        # Then try file path (for development)
        elif self.cloudfront_private_key_path and os.path.exists(self.cloudfront_private_key_path):
            try:
                with open(self.cloudfront_private_key_path, 'r') as f:
                    key_content = f.read()
                key_source = f"file {self.cloudfront_private_key_path}"
            except Exception as e:
                raise ValueError(
                    f"Failed to load CloudFront private key from file {self.cloudfront_private_key_path}: {str(e)}"
                )
        else:
            raise ValueError(
                "CloudFront private key not found. "
                "Please set either CLOUDFRONT_PRIVATE_KEY_CONTENT (for deployed environments) "
                "or CLOUDFRONT_PRIVATE_KEY_PATH (for development) in .env"
            )
        
        # Validate key content
        if not key_content or not key_content.startswith('-----BEGIN'):
            raise ValueError(
                f"Invalid PEM file format in {key_source}: does not start with '-----BEGIN'. "
                f"If using CLOUDFRONT_PRIVATE_KEY_CONTENT, ensure it has proper newlines (not escaped \\n)"
            )
        
        self.private_key_content = key_content.encode() if isinstance(key_content, str) else key_content
    
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
        """Load RSA private key from stored content."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        try:
            private_key = serialization.load_pem_private_key(
                self.private_key_content,
                password=None,
                backend=default_backend()
            )
            return private_key
        except Exception as e:
            raise ValueError(
                f"Failed to load CloudFront private key: {str(e)}"
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
