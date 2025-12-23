from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VideoViewSet, update_video_encoding_status

router = DefaultRouter()
router.register(r'', VideoViewSet, basename='video')

urlpatterns = [
    path('', include(router.urls)),
    # Worker notification endpoint (no authentication required)
    path('<uuid:video_id>/update-encoding-status/', update_video_encoding_status, name='update-encoding-status'),
]
