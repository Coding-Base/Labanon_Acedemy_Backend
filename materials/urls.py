# backend/materials/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MaterialViewSet

# Create router and register viewsets
router = DefaultRouter()
router.register(r'materials', MaterialViewSet, basename='material')

urlpatterns = [
    path('', include(router.urls)),
]
