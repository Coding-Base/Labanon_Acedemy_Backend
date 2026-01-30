from django.conf import settings

class SecurityHeadersMiddleware:
    """Middleware to add common security headers to all responses."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # X-Content-Type-Options
        response.setdefault('X-Content-Type-Options', 'nosniff')
        # X-Frame-Options (also set via settings)
        response.setdefault('X-Frame-Options', getattr(settings, 'X_FRAME_OPTIONS', 'DENY'))
        # X-XSS-Protection (legacy)
        response.setdefault('X-XSS-Protection', '1; mode=block')
        # Referrer-Policy
        response.setdefault('Referrer-Policy', getattr(settings, 'SECURE_REFERRER_POLICY', 'no-referrer-when-downgrade'))
        # Permissions-Policy (formerly Feature-Policy) - tighten to disallow powerful features
        response.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')

        # Content-Security-Policy: conservative default that allows site's own resources and trusted CDNs
        # Adjust as needed for your frontend assets and CDNs. Keep minimal to reduce XSS surface.
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' https://api.lighthubacademy.org http://localhost:8000;"
        )
        # Only attach CSP if not in debug or if FORCE_CSP in env
        if not settings.DEBUG or getattr(settings, 'FORCE_CSP', False):
            response.setdefault('Content-Security-Policy', csp)

        # HSTS header - only include if enabled
        if not settings.DEBUG and getattr(settings, 'SECURE_HSTS_SECONDS', 0):
            response.setdefault('Strict-Transport-Security', f"max-age={settings.SECURE_HSTS_SECONDS}; includeSubDomains; preload")

        return response
