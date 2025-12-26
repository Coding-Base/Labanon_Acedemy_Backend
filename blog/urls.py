from rest_framework.routers import DefaultRouter
from .views import BlogViewSet, BlogCommentViewSet

router = DefaultRouter()
router.register(r'comments', BlogCommentViewSet, basename='blog-comment')
router.register(r'', BlogViewSet, basename='blog')

urlpatterns = router.urls
