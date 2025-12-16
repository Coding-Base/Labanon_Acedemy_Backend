from rest_framework import viewsets, permissions, status, filters
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage
import uuid
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from .models import Institution, Course, Module, Lesson, Enrollment, CartItem
from .serializers import InstitutionSerializer, CourseSerializer, ModuleSerializer, LessonSerializer, EnrollmentSerializer, CartItemSerializer
from .permissions import IsCreatorOrTeacherOrAdmin
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .serializers import PaymentSerializer
from .models import Payment
from django.conf import settings
from django.utils.text import slugify
import random
import string


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().order_by('-created_at')
    serializer_class = CourseSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'description', 'creator__username', 'institution__name']
    filterset_fields = ['published', 'price', 'institution', 'creator']
    ordering_fields = ['created_at', 'price', 'title']

    def perform_create(self, serializer):
        # assign the creator automatically and generate a unique slug from title
        title = serializer.validated_data.get('title', '')
        base_slug = slugify(title) or 'course'
        slug = base_slug
        # ensure uniqueness
        i = 0
        while Course.objects.filter(slug=slug).exists():
            i += 1
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            slug = f"{base_slug}-{suffix}"

        serializer.save(creator=self.request.user, slug=slug)


class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]

    def perform_create(self, serializer):
        # ensure the creator owns the course or is staff
        course = serializer.validated_data.get('course')
        if course and course.creator != self.request.user and not self.request.user.is_staff:
            # prevent creating modules for courses the user doesn't own
            raise permissions.PermissionDenied('You do not own this course')
        serializer.save()


class LessonViewSet(viewsets.ModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]

    def perform_create(self, serializer):
        module = serializer.validated_data.get('module')
        if module and module.course.creator != self.request.user and not self.request.user.is_staff:
            raise permissions.PermissionDenied('You do not own this module/course')
        serializer.save()


class LessonMediaUploadView(APIView):
    permission_classes = [IsCreatorOrTeacherOrAdmin, IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, format=None):
        # expecting a 'file' form field
        upload = request.FILES.get('file')
        if not upload:
            return JsonResponse({'detail': 'No file provided'}, status=400)

        # create unique filename
        ext = upload.name.split('.')[-1]
        name = f"lessons/{uuid.uuid4().hex}.{ext}"

        saved_name = default_storage.save(name, upload)
        url = default_storage.url(saved_name)
        return JsonResponse({'name': saved_name, 'url': url})


class CourseImageUploadView(APIView):
    permission_classes = [IsCreatorOrTeacherOrAdmin, IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, format=None):
        upload = request.FILES.get('file')
        if not upload:
            return JsonResponse({'detail': 'No file provided'}, status=400)

        ext = upload.name.split('.')[-1]
        name = f"courses/{uuid.uuid4().hex}.{ext}"
        saved_name = default_storage.save(name, upload)
        url = default_storage.url(saved_name)
        return JsonResponse({'name': saved_name, 'url': url})


class InstitutionViewSet(viewsets.ModelViewSet):
    queryset = Institution.objects.all()
    serializer_class = InstitutionSerializer
    permission_classes = [IsCreatorOrTeacherOrAdmin]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class EnrollmentViewSet(viewsets.ModelViewSet):
    queryset = Enrollment.objects.all()
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Enrollment.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # When creating an enrollment, if the course is free, mark as purchased immediately
        course = serializer.validated_data.get('course')
        user = self.request.user
        enrollment = serializer.save(user=user)
        if course and float(course.price) == 0:
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            # create a successful Payment record for bookkeeping
            Payment.objects.create(
                user=user,
                course=course,
                amount=0,
                platform_fee=0,
                kind=Payment.KIND_COURSE,
                status=Payment.SUCCESS,
            )

    @action(detail=True, methods=['post'])
    def purchase(self, request, pk=None):
        """Initiate a purchase for an enrollment. This is a stub for real payment integration.

        Creates a Payment object with status pending and returns a fake payment_url.
        Real integration with Paystack will replace this.
        """
        enrollment = self.get_object()
        if enrollment.purchased:
            return Response({'detail': 'Already purchased'}, status=status.HTTP_400_BAD_REQUEST)

        course = enrollment.course
        amount = float(course.price)

        # If course is free, mark enrollment purchased immediately
        if amount == 0:
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            Payment.objects.create(
                user=request.user,
                course=course,
                amount=0,
                platform_fee=0,
                kind=Payment.KIND_COURSE,
                status=Payment.SUCCESS,
            )
            return Response({'detail': 'Enrollment completed (free course)'} , status=status.HTTP_200_OK)

        # calculate platform fee from settings
        commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
        platform_fee = float(amount) * float(commission)

        payment = Payment.objects.create(
            user=request.user,
            course=course,
            amount=amount,
            platform_fee=platform_fee,
            status=Payment.PENDING,
            kind=Payment.KIND_COURSE,
        )

        # In a real implementation we would create a Paystack transaction and return the payment link.
        fake_payment_url = f"https://pay.example.com/checkout/{payment.id}"

        serializer = PaymentSerializer(payment)
        return Response({'payment': serializer.data, 'payment_url': fake_payment_url})


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """Allow users to view their own payments (paginated)."""
    queryset = Payment.objects.all().order_by('-created_at')
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by('-created_at')


class CartItemViewSet(viewsets.ModelViewSet):
    """Manage cart items for the authenticated user."""
    queryset = CartItem.objects.all().order_by('-added_at')
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).order_by('-added_at')

    def perform_create(self, serializer):
        # attach current user
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def checkout(self, request, pk=None):
        """Checkout a single cart item: creates a Payment and returns a payment_url (stub)."""
        cart_item = self.get_object()
        course = cart_item.course
        amount = float(course.price)

        if amount == 0:
            # create enrollment and mark purchased immediately
            enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
            enrollment.purchased = True
            enrollment.purchased_at = timezone.now()
            enrollment.save()
            Payment.objects.create(
                user=request.user,
                course=course,
                amount=0,
                platform_fee=0,
                kind=Payment.KIND_COURSE,
                status=Payment.SUCCESS,
            )
            # remove cart item
            cart_item.delete()
            return Response({'detail': 'Enrolled (free course)'} , status=status.HTTP_200_OK)

        commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
        platform_fee = float(amount) * float(commission)

        payment = Payment.objects.create(
            user=request.user,
            course=course,
            amount=amount,
            platform_fee=platform_fee,
            status=Payment.PENDING,
            kind=Payment.KIND_COURSE,
        )

        fake_payment_url = f"https://pay.example.com/checkout/{payment.id}"

        serializer = PaymentSerializer(payment)
        return Response({'payment': serializer.data, 'payment_url': fake_payment_url})

    @action(detail=False, methods=['post'])
    def checkout_all(self, request):
        """Checkout all cart items for the user. Returns list of payment links or completes free enrollments."""
        items = self.get_queryset()
        payments = []
        for item in items:
            course = item.course
            amount = float(course.price)
            if amount == 0:
                enrollment, _ = Enrollment.objects.get_or_create(user=request.user, course=course)
                enrollment.purchased = True
                enrollment.purchased_at = timezone.now()
                enrollment.save()
                Payment.objects.create(
                    user=request.user,
                    course=course,
                    amount=0,
                    platform_fee=0,
                    kind=Payment.KIND_COURSE,
                    status=Payment.SUCCESS,
                )
                item.delete()
            else:
                commission = getattr(settings, 'PLATFORM_COMMISSION', 0.05)
                platform_fee = float(amount) * float(commission)
                payment = Payment.objects.create(
                    user=request.user,
                    course=course,
                    amount=amount,
                    platform_fee=platform_fee,
                    status=Payment.PENDING,
                    kind=Payment.KIND_COURSE,
                )
                payments.append({'payment_id': payment.id, 'payment_url': f"https://pay.example.com/checkout/{payment.id}", 'course': course.id})

        return Response({'payments': payments})
