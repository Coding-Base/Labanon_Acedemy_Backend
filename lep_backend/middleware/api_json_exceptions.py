from django.http import JsonResponse
import traceback

class ApiJsonExceptionMiddleware:
    """Convert HTML debug/error pages into safe JSON responses for API paths.

    - For API requests (paths starting with /api/), return a JSON 404 instead of the
      Django debug HTML when a URL isn't found.
    - Catch unhandled exceptions during request processing and return a JSON 500.

    This prevents sensitive debug HTML from being served to API clients when
    DEBUG=True.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)

            # If an API path produced an HTML 404 (Django debug page), return JSON instead
            content_type = response.get('Content-Type', '')
            if request.path.startswith('/api/') and response.status_code == 404 and 'text/html' in content_type:
                return JsonResponse({'detail': 'Not found.'}, status=404)

            return response
        except Exception as exc:
            # For API endpoints, hide debug HTML and return a safe JSON error
            if request.path.startswith('/api/'):
                print('[API ERROR]', str(exc))
                traceback.print_exc()
                return JsonResponse({'detail': 'Internal server error'}, status=500)
            # For non-API requests, re-raise to allow Django debug pages in development
            raise
