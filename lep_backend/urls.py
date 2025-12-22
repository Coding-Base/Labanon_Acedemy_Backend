from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.contrib import admin
from users.views import DashboardView
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/', include('courses.urls')),
    path('api/cbt/', include('cbt.urls')),
    path('api/videos/', include('videos.urls')),
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
]

# Serve media files in development (only when DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Extra mapping: some of your existing images live inside the app folder 'courses/'
    # (e.g., backend/courses/<file>). Serve that folder at /media/courses/ so older files
    # placed in the app directory are accessible via the same /media/courses/ URL.
    import os
    app_courses_dir = os.path.join(settings.BASE_DIR, 'courses')
    urlpatterns += static('/media/courses/', document_root=app_courses_dir)
