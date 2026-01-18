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
    path('api/admin/', include('users.urls')),  # Admin routes
    path('api/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/', include('courses.urls')),
    path('api/cbt/', include('cbt.urls')),
    path('api/videos/', include('videos.urls')),
    path('api/blog/', include('blog.urls')),
    path('api/subadmin/', include('subadmin.urls')),
    path('api/messages/', include('messaging.urls')),
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
]

# Serve media files in development (only when DEBUG=True)
if settings.DEBUG:
    # Always serve local media files at /media/ during development so files
    # stored under backend/media/ are reachable even when MEDIA_URL is set
    # to a full S3/CloudFront URL via environment variables.
    urlpatterns += static('/media/', document_root=settings.MEDIA_ROOT)

    # Extra mapping: some legacy images live inside the app folder 'courses/'
    # (e.g., backend/courses/<file>). Serve that folder at /media/courses/
    # so older files placed in the app directory remain accessible.
    import os
    app_courses_dir = os.path.join(settings.BASE_DIR, 'courses')
    urlpatterns += static('/media/courses/', document_root=app_courses_dir)
