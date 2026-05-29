from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import MessageViewSet, ContactAPIView, DirectMessageViewSet, UserSearchView, AdminEmailBroadcastView

# Create separate routers for different prefixes
support_router = DefaultRouter()
support_router.register(r'', MessageViewSet, basename='message')

direct_router = DefaultRouter()
direct_router.register(r'', DirectMessageViewSet, basename='direct-message')

# Place explicit routes before the router-generated patterns to avoid
# accidental capture by the ViewSet detail lookup (e.g. 'contact' as a pk).
urlpatterns = [
    path('broadcast-email/', AdminEmailBroadcastView.as_view(), name='broadcast-email'),
    path('contact/', ContactAPIView.as_view(), name='contact'),
    path('users/search/', UserSearchView.as_view(), name='user-search'),
    path('direct/', include(direct_router.urls)),  # Direct messages at /api/messages/direct/
]

urlpatterns += support_router.urls  # Support/inbox messages at /api/messages/
