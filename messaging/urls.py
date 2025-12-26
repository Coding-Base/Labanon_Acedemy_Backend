from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import MessageViewSet

router = DefaultRouter()
router.register(r'', MessageViewSet, basename='message')

urlpatterns = router.urls
