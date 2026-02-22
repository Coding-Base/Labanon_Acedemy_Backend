from rest_framework.routers import DefaultRouter
from .views import PromoCodeViewSet

router = DefaultRouter()
router.register(r'promocodes', PromoCodeViewSet, basename='promocode')

urlpatterns = router.urls
