from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import MessageViewSet, ContactAPIView

router = DefaultRouter()
router.register(r'', MessageViewSet, basename='message')

# Place explicit routes before the router-generated patterns to avoid
# accidental capture by the ViewSet detail lookup (e.g. 'contact' as a pk).
urlpatterns = [
    path('contact/', ContactAPIView.as_view(), name='contact'),
]

urlpatterns += router.urls
