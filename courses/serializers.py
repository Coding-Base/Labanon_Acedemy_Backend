from rest_framework import serializers
from .models import Institution, Course, Module, Lesson, Enrollment, Payment, CartItem


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = '__all__'


class LessonSerializer(serializers.ModelSerializer):
    module = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all(), required=False)

    class Meta:
        model = Lesson
        fields = ['id', 'module', 'title', 'content', 'video', 'order']


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

    def get_image(self, obj):
        raw = obj.image or ''
        if not raw:
            return ''
        # if already absolute, return as-is
        if raw.startswith('http://') or raw.startswith('https://'):
            return raw

        request = self.context.get('request')
        # if serializer has request context, build absolute uri
        if request is not None:
            # if raw already begins with '/', build_absolute_uri will join domain + path
            return request.build_absolute_uri(raw if raw.startswith('/') else f'/{raw}')

        # fallback: return raw (frontend will try to resolve)
        return raw


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
