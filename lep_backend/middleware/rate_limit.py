from django.core.cache import caches
from django.conf import settings
from django.http import HttpResponse

class RateLimitMiddleware:
    """Simple IP-based rate limiting middleware using Django cache (Redis recommended).

    Behavior:
    - Counts requests per IP within a window.
    - If count exceeds RATE_LIMIT_MAX_REQUESTS, the IP is temporarily banned for RATE_LIMIT_BAN_SECONDS.
    - Uses cache keys: 'rl:<ip>' and 'rl:banned:<ip>'.

    Note: This is a best-effort protection; a robust deployment should also
    use infrastructure rate-limiting (nginx, cloudflare, WAF) and connection-level protections.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            self.cache = caches['default']
        except Exception:
            self.cache = None
        self.max_requests = getattr(settings, 'RATE_LIMIT_MAX_REQUESTS', 300)
        self.window = getattr(settings, 'RATE_LIMIT_WINDOW_SECONDS', 300)
        self.ban_seconds = getattr(settings, 'RATE_LIMIT_BAN_SECONDS', 600)

    def _get_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            # X-Forwarded-For can contain multiple IPs, take first
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def __call__(self, request):
        if not self.cache:
            return self.get_response(request)

        ip = self._get_ip(request)
        if not ip:
            return self.get_response(request)

        banned_key = f"rl:banned:{ip}"
        if self.cache.get(banned_key):
            return HttpResponse('Too many requests', status=429)

        key = f"rl:{ip}"
        # Use add to initialize atomically if not present
        added = self.cache.add(key, 1, timeout=self.window)
        if not added:
            try:
                self.cache.incr(key)
            except Exception:
                # Some cache backends may not implement incr; fall back to read-set
                val = self.cache.get(key) or 0
                self.cache.set(key, val + 1, timeout=self.window)

        count = self.cache.get(key) or 0
        if count > self.max_requests:
            # ban
            self.cache.set(banned_key, 1, timeout=self.ban_seconds)
            return HttpResponse('Too many requests', status=429)

        return self.get_response(request)
