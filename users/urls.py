from django.urls import path
from .views import RegisterView, MeView, UserAdminViewSet, ChangePasswordView, ProfileUpdateView, DashboardView, TrialDaysView, ReviewsPublicView, ReviewDetailView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import PasswordResetRequestView, PasswordResetConfirmView
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'users', UserAdminViewSet, basename='admin-user')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('trial-days/', TrialDaysView.as_view(), name='trial-days'),
    path('reviews/', ReviewsPublicView.as_view(), name='reviews'),
    path('reviews/<int:pk>/', ReviewDetailView.as_view(), name='review-detail'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('profile-update/', ProfileUpdateView.as_view(), name='profile_update'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]


urlpatterns += router.urls


