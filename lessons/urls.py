# backend/lessons/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, SubjectViewSet, LessonSubfolderViewSet, TopicViewSet, LessonContentViewSet,
    StudentLessonProgressViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'subfolders', LessonSubfolderViewSet, basename='lesson-subfolder')
router.register(r'topics', TopicViewSet, basename='topic')
router.register(r'lessons', LessonContentViewSet, basename='lesson')
router.register(r'progress', StudentLessonProgressViewSet, basename='progress')

urlpatterns = [
    path('', include(router.urls)),
]
