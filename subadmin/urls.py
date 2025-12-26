from rest_framework.routers import DefaultRouter
from .views import SubAdminViewSet

router = DefaultRouter()
router.register(r'', SubAdminViewSet, basename='subadmin')

urlpatterns = router.urls
