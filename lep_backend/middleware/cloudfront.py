"""
CloudFront origin verification middleware.

This was previously implemented in `lep_backend/middleware.py` as a module.
To support the dotted import `lep_backend.middleware.CloudFrontOriginMiddleware`
we now place the class inside the `lep_backend.middleware` package and
re-export it from `__init__.py`.
"""
import logging
from django.conf import settings
from django.http import HttpResponseForbidden

logger = logging.getLogger(__name__)


class CloudFrontOriginMiddleware:
    """
    Optional middleware to verify CloudFront origin custom header.

    ONLY EFFECTIVE if CloudFront OAI (Origin Access Identity) is configured.
    Free tier CloudFront doesn't support OAI - use signed URLs instead.

    If enabled, verifies requests to video paths contain the X-Origin-Verify header
    that CloudFront adds when configured with custom origin headers.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.origin_secret = getattr(settings, 'CLOUDFRONT_ORIGIN_SECRET', '')
        self.enabled = bool(self.origin_secret)

        if not self.enabled:
            logger.info('CloudFront origin verification disabled (CLOUDFRONT_ORIGIN_SECRET not configured)')

    def __call__(self, request):
        # Skip validation if not configured (free tier scenario)
        if not self.enabled:
            return self.get_response(request)

        # Only validate requests to video streaming paths
        if not self.should_validate_header(request):
            return self.get_response(request)

        # Check for X-Origin-Verify header from CloudFront
        origin_header = request.META.get('HTTP_X_ORIGIN_VERIFY', '')

        if origin_header != self.origin_secret:
            logger.warning(
                f"Invalid origin header on {request.path} from {request.META.get('REMOTE_ADDR', 'unknown')}. "
                f"This indicates a direct S3 access attempt (not through CloudFront)."
            )
            return HttpResponseForbidden('Invalid origin header')

        response = self.get_response(request)
        return response

    def should_validate_header(self, request):
        """Determine if this request should have the origin header."""
        # Only validate requests to video streaming (not API requests)
        if request.path.startswith('/videos/'):
            return True

        # Don't validate API requests
        if request.path.startswith('/api/'):
            return False

        return False
