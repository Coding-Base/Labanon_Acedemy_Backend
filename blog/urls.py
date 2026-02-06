from rest_framework.routers import DefaultRouter
from .views import BlogViewSet, BlogCommentViewSet, upload_blog_image
from django.urls import path

router = DefaultRouter()
router.register(r'comments', BlogCommentViewSet, basename='blog-comment')
router.register(r'', BlogViewSet, basename='blog')

# IMPORTANT: upload-image/ MUST come BEFORE router.urls because router's empty pattern catches everything
urlpatterns = [
	path('upload-image/', upload_blog_image, name='blog-upload-image'),
] + router.urls
