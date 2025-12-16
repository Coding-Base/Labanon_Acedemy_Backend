from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.contrib import admin
from users.views import DashboardView
from users.views import UserAdminViewSet

router = DefaultRouter()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/', include('courses.urls')),
    path('api/cbt/', include('cbt.urls')),
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
]

# Register a small router for master-admin user endpoints at /api/admin/users/
admin_router = DefaultRouter()
