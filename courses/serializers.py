# backend/courses/serializers.py
from rest_framework import serializers
from django.conf import settings
import re

from .models import Institution, Course, Module, Lesson, Enrollment, Payment, CartItem


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = '__all__'


class LessonSerializer(serializers.ModelSerializer):
    module = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all(), required=False)
    video_s3_url = serializers.SerializerMethodField(read_only=True)
    video_s3_status = serializers.CharField(source='video_s3.status', read_only=True, allow_null=True)

    class Meta:
        model = Lesson
        fields = ['id', 'module', 'title', 'content', 'video', 'video_s3', 'video_s3_url', 'video_s3_status', 'youtube_url', 'order']
    
    def get_video_s3_url(self, obj):
        """Return CloudFront URL if video_s3 exists and is ready."""
        if obj.video_s3 and obj.video_s3.status == 'ready':
            return obj.video_s3.cloudfront_url
        return None


class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ['id', 'course', 'title', 'order', 'lessons']


class CourseSerializer(serializers.ModelSerializer):
    modules = ModuleSerializer(many=True, read_only=True)
    creator = serializers.StringRelatedField()
    slug = serializers.SlugField(read_only=True)
    # return absolute image URL when possible
    image = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['id', 'title', 'slug', 'image', 'description', 'price', 'published', 'creator', 'modules']

    def _normalize_path(self, raw: str) -> str:
        """
        Normalize the stored image path so we don't end up with duplicate
        '/media/media/...' or missing leading slash issues.
        Returns a path that starts with a single '/media/' followed by the relative path.
        """
        if not raw:
            return ''

        raw = raw.strip()

        # If it's a full URL, return as-is later (caller checks)
        if raw.startswith('http://') or raw.startswith('https://'):
            return raw

        # If the stored value contains the SITE_URL, remove it so we only have the path
        site = getattr(settings, 'SITE_URL', '').rstrip('/')
        if site and raw.startswith(site):
            raw = raw[len(site):]

        # Collapse repeated "/media/" segments (e.g. "/media/media/courses/.." -> "/media/courses/..")
        # Also handle raw that may be like "media/courses/..."
        # Ensure it starts with a single leading slash.
        # We'll use regex to collapse repeated /media/ occurrences.
        raw = re.sub(r'(^/+)', '/', raw)  # ensure single leading slash
        # replace repeated 'media' segments like /media/media/... -> /media/...
        raw = re.sub(r'(\/media\/)+', '/media/', raw)

        # If after normalization it doesn't start with /media/, ensure media prefix exists
        media_prefix = settings.MEDIA_URL.rstrip('/')  # normally '/media'
        if not raw.startswith(media_prefix):
            # strip leading slashes and prefix MEDIA_URL
            raw = f"{media_prefix}/{raw.lstrip('/')}"
        return raw

    def get_image(self, obj):
        raw = (obj.image or '').strip()
        if not raw:
            return ''

        # If already absolute URL, return as-is
        if raw.startswith('http://') or raw.startswith('https://'):
            return raw

        # Normalize raw path to a single path starting with /media/...
        normalized = self._normalize_path(raw)

        request = self.context.get('request')
        # if serializer has request context, build absolute uri
        if request is not None:
            # request.build_absolute_uri expects a path (leading slash ok)
            return request.build_absolute_uri(normalized)

        # fallback: build with SITE_URL (ensure no double slashes)
        site = getattr(settings, 'SITE_URL', '').rstrip('/')
        if site:
            return f"{site}{normalized}"
        # as a last fallback return normalized path (frontend should resolve)
        return normalized


class EnrollmentSerializer(serializers.ModelSerializer):
    # return nested course data for convenience in frontend lists
    course = CourseSerializer(read_only=True)
    # allow creating/updating by passing course_id
    course_id = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), write_only=True, source='course')

    class Meta:
        model = Enrollment
        fields = ['id', 'course', 'course_id', 'purchased', 'purchased_at']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'user', 'course', 'amount', 'kind', 'platform_fee', 'provider_reference', 'status', 'created_at']
        read_only_fields = ['platform_fee', 'status', 'created_at']


class CartItemSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'course', 'course_id', 'added_at']
        extra_kwargs = {
            'course_id': {'write_only': True}
        }

    # accept course_id on create
    course_id = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), write_only=True, source='course')
