# backend/courses/serializers.py
from rest_framework import serializers
from django.conf import settings
from django.db.models import Avg, Sum 
from django.core.files.storage import default_storage
import re
import uuid
import os

from .models import (
    Institution, Course, Module, Lesson, Enrollment, Payment, 
    CartItem, Diploma, DiplomaEnrollment, Portfolio, 
    PortfolioGalleryItem, Certificate, Review, GospelVideo
)

class InstitutionSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    courses_count = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = [
            'id', 'owner_username', 'name', 'description', 'is_active', 
            'courses_count', 'created_at', 'signer_name', 'signer_position','signature_image'
        ]
        read_only_fields = ['id', 'owner_username', 'courses_count', 'created_at']

    def get_courses_count(self, obj):
        return obj.courses.count()


class LessonSerializer(serializers.ModelSerializer):
    module = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all(), required=False)
    video_s3_url = serializers.SerializerMethodField(read_only=True)
    video_s3_status = serializers.CharField(source='video_s3.status', read_only=True, allow_null=True)

    class Meta:
        model = Lesson
        fields = [
            'id', 'module', 'title', 'content', 'video', 'video_s3', 
            'video_s3_url', 'video_s3_status', 'youtube_url', 'duration_minutes', 'order'
        ]
    
    def get_video_s3_url(self, obj):
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
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    institution_name = serializers.CharField(source='institution.name', read_only=True, allow_null=True)
    slug = serializers.SlugField(read_only=True)
    
    image = serializers.SerializerMethodField()
    image_upload = serializers.FileField(write_only=True, required=False)

    stats = serializers.SerializerMethodField()

    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    meeting_time = serializers.TimeField(required=False, allow_null=True)
    meeting_place = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    meeting_link = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'image', 'image_upload', 'description', 'price', 
            'published', 'creator', 'creator_username', 
            'institution', 'institution_name',  # <--- FIXED: Added 'institution' ID here
            'created_at', 'modules', 'stats', 
            'start_date', 'end_date', 'meeting_time', 'meeting_place', 'meeting_link'
        ]

    def get_stats(self, obj):
        reviews = obj.reviews.all()
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
        ratings_count = reviews.count()
        students_count = obj.enrollments.filter(purchased=True).count()
        total_minutes = Lesson.objects.filter(module__course=obj).aggregate(total=Sum('duration_minutes'))['total'] or 0
        hours = total_minutes // 60
        minutes = total_minutes % 60
        duration_str = f"{int(hours)}h {int(minutes)}m"

        return {
            'rating': round(avg_rating, 1),
            'ratings_count': ratings_count,
            'students': students_count,
            'duration': duration_str
        }

    def _normalize_path(self, raw: str) -> str:
        if not raw: return ''
        raw = raw.strip()
        if raw.startswith('http://') or raw.startswith('https://'): return raw
        site = getattr(settings, 'SITE_URL', '').rstrip('/')
        if site and raw.startswith(site): raw = raw[len(site):]
        raw = re.sub(r'(^/+)', '/', raw)
        raw = re.sub(r'(\/media\/)+', '/media/', raw)
        media_prefix = settings.MEDIA_URL.rstrip('/')
        if not raw.startswith(media_prefix):
            raw = f"{media_prefix}/{raw.lstrip('/')}"
        return raw

    def get_image(self, obj):
        raw = (obj.image or '').strip()
        if not raw: return ''
        if raw.startswith('http://') or raw.startswith('https://'): return raw
        normalized = self._normalize_path(raw)
        request = self.context.get('request')
        if request is not None: return request.build_absolute_uri(normalized)
        site = getattr(settings, 'SITE_URL', '').rstrip('/')
        if site: return f"{site}{normalized}"
        return normalized

    def create(self, validated_data):
        image_file = validated_data.pop('image_upload', None)
        course = super().create(validated_data)
        if image_file:
            self._handle_image_upload(course, image_file)
        return course

    def update(self, instance, validated_data):
        image_file = validated_data.pop('image_upload', None)
        course = super().update(instance, validated_data)
        if image_file:
            self._handle_image_upload(course, image_file)
        return course

    def _handle_image_upload(self, course, image_file):
        try:
            ext = image_file.name.split('.')[-1]
            name = f"courses/{uuid.uuid4().hex}.{ext}"
            saved_name = default_storage.save(name, image_file)
            
            try:
                url = default_storage.url(saved_name)
            except Exception:
                url = f"{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
            
            if url.startswith('/') and getattr(settings, 'SITE_URL', None):
                url = f"{settings.SITE_URL.rstrip('/')}{url}"
                
            course.image = url
            course.save()
        except Exception as e:
            print(f"Error saving course image: {e}")


class EnrollmentSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), write_only=True, source='course')

    class Meta:
        model = Enrollment
        fields = ['id', 'course', 'course_id', 'purchased', 'purchased_at']


class PaymentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True, allow_null=True)
    diploma_title = serializers.CharField(source='diploma.title', read_only=True, allow_null=True)
    gateway = serializers.CharField(source='payment_provider', read_only=True)
    reference = serializers.SerializerMethodField()
    merchant_fee = serializers.DecimalField(source='platform_fee', max_digits=10, decimal_places=2, read_only=True)
    gateway_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    net_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'course', 'course_title', 'diploma', 'diploma_title',
            'amount', 'kind', 'platform_fee', 'creator_amount', 'paystack_reference',
            'provider_reference', 'payment_provider', 'gateway', 'reference', 'merchant_fee',
            'gateway_fee', 'net_amount', 'status', 'created_at', 'verified_at'
        ]
        read_only_fields = ['platform_fee', 'creator_amount', 'gateway_fee', 'net_amount', 'status', 'created_at', 'verified_at']

    def get_reference(self, obj):
        """Return the appropriate reference based on payment provider"""
        if obj.payment_provider == 'paystack':
            return obj.paystack_reference
        elif obj.payment_provider == 'flutterwave':
            return obj.flutterwave_reference or obj.flutterwave_transaction_id
        return obj.provider_reference


class CartItemSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), write_only=True, source='course')

    class Meta:
        model = CartItem
        fields = ['id', 'course', 'course_id', 'added_at']
        extra_kwargs = {
            'course_id': {'write_only': True}
        }


class DiplomaSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(source='institution.name', read_only=True)
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    
    image = serializers.SerializerMethodField()
    image_upload = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = Diploma
        fields = [
            'id', 'institution', 'institution_name', 'creator', 'creator_username',
            'title', 'slug', 'description', 'image', 'image_upload', 'price', 'duration',
            'start_date', 'end_date', 'meeting_place', 'published', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def _normalize_path(self, raw: str) -> str:
        if not raw: return ''
        raw = raw.strip()
        if raw.startswith('http://') or raw.startswith('https://'): return raw
        site = getattr(settings, 'SITE_URL', '').rstrip('/')
        if site and raw.startswith(site): raw = raw[len(site):]
        raw = re.sub(r'(^/+)', '/', raw)
        raw = re.sub(r'(\/media\/)+', '/media/', raw)
        media_prefix = settings.MEDIA_URL.rstrip('/')
        if not raw.startswith(media_prefix):
            raw = f"{media_prefix}/{raw.lstrip('/')}"
        return raw

    def get_image(self, obj):
        raw = (obj.image or '').strip()
        if not raw: return ''
        if raw.startswith('http://') or raw.startswith('https://'): return raw
        normalized = self._normalize_path(raw)
        request = self.context.get('request')
        if request is not None: return request.build_absolute_uri(normalized)
        site = getattr(settings, 'SITE_URL', '').rstrip('/')
        if site: return f"{site}{normalized}"
        return normalized

    def create(self, validated_data):
        image_file = validated_data.pop('image_upload', None)
        diploma = super().create(validated_data)
        if image_file:
            self._handle_image_upload(diploma, image_file)
        return diploma

    def update(self, instance, validated_data):
        image_file = validated_data.pop('image_upload', None)
        diploma = super().update(instance, validated_data)
        if image_file:
            self._handle_image_upload(diploma, image_file)
        return diploma

    def _handle_image_upload(self, diploma, image_file):
        try:
            ext = image_file.name.split('.')[-1]
            name = f"diplomas/{uuid.uuid4().hex}.{ext}"
            saved_name = default_storage.save(name, image_file)
            try:
                url = default_storage.url(saved_name)
            except Exception:
                url = f"{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
            
            if url.startswith('/') and getattr(settings, 'SITE_URL', None):
                url = f"{settings.SITE_URL.rstrip('/')}{url}"
                
            diploma.image = url
            diploma.save()
        except Exception as e:
            print(f"Error saving diploma image: {e}")


class DiplomaEnrollmentSerializer(serializers.ModelSerializer):
    diploma = DiplomaSerializer(read_only=True)
    diploma_id = serializers.PrimaryKeyRelatedField(queryset=Diploma.objects.all(), write_only=True, source='diploma')
    user = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DiplomaEnrollment
        fields = ['id', 'user', 'diploma', 'diploma_id', 'purchased', 'purchased_at', 'completed', 'completed_at']

    def get_user(self, obj):
        return obj.user.id if obj.user else None


class PortfolioGalleryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioGalleryItem
        fields = ['id', 'portfolio', 'title', 'description', 'image', 'url', 'order', 'created_at']


class PortfolioSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(source='institution.name', read_only=True)
    gallery_items = PortfolioGalleryItemSerializer(many=True, read_only=True)

    class Meta:
        model = Portfolio
        fields = [
            'id', 'institution', 'institution_name', 'title', 'description', 'overview',
            'image', 'website', 'location', 'phone', 'email', 'theme_color', 'published', 'public_token',
            'gallery_items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['public_token', 'created_at', 'updated_at', 'gallery_items']

class CertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'id', 'user_id', 'username', 'course', 'course_title', 'certificate_id',
            'issue_date', 'completion_date', 'is_downloaded', 'download_count',
            'last_downloaded_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user_id', 'username', 'certificate_id', 'issue_date',
            'download_count', 'last_downloaded_at', 'created_at', 'updated_at'
        ]


class GospelVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GospelVideo
        fields = [
            'id', 'youtube_url', 'scheduled_time', 'title', 'description',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']