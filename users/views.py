from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import User
from .serializers import UserSerializer, RegisterSerializer
from rest_framework.views import APIView
from rest_framework import viewsets, mixins
from rest_framework import permissions as drf_permissions
from rest_framework import filters
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum
from courses.models import Course, Enrollment, Payment
from cbt.models import ExamAttempt
from .serializers import UserSerializer
from .permissions import IsMasterAdmin


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = user.role
        data = {'role': role, 'username': user.username}

        if role == User.TUTOR:
            courses_qs = Course.objects.filter(creator=user)
            courses_count = courses_qs.count()
            # total sales (sum of successful payments for those courses)
            sales = Payment.objects.filter(course__in=courses_qs, status=Payment.SUCCESS).aggregate(total=Sum('amount'))['total'] or 0
            students = Enrollment.objects.filter(course__in=courses_qs, purchased=True).values('user').distinct().count()
            data.update({'courses_count': courses_count, 'sales_total': float(sales), 'students_count': students})

        elif role == User.STUDENT:
            enrollments = Enrollment.objects.filter(user=user)
            enroll_count = enrollments.count()
            attempts = ExamAttempt.objects.filter(user=user)
            attempts_count = attempts.count()
            avg_score = attempts.aggregate(avg=Sum('score'))['avg'] if attempts_count else None
            data.update({'enrollments_count': enroll_count, 'attempts_count': attempts_count, 'avg_score': float(avg_score) if avg_score else None})

        elif role == User.INSTITUTION:
            # Fix: Ensure we look at owned institutions properly
            inst_qs = user.owned_institutions.all()
            inst_count = inst_qs.count()
            
            # Courses linked to ANY of the user's institutions
            courses_qs = Course.objects.filter(institution__in=inst_qs)
            courses_count = courses_qs.count()
            
            # Students: Count unique users enrolled in this institution's courses OR diplomas
            # (Assuming Enrollment and DiplomaEnrollment models exist)
            student_ids = set()
            
            # 1. Students in Online Courses
            course_students = Enrollment.objects.filter(course__institution__in=inst_qs).values_list('user', flat=True)
            student_ids.update(course_students)
            
            # 2. Students in Diplomas (if applicable)
            # Assuming DiplomaEnrollment links to Diploma which links to Institution
            try:
                from courses.models import DiplomaEnrollment
                diploma_students = DiplomaEnrollment.objects.filter(diploma__institution__in=inst_qs).values_list('user', flat=True)
                student_ids.update(diploma_students)
            except ImportError:
                pass

            data.update({
                'institutions_count': inst_count, 
                'courses_count': courses_count, 
                'students_count': len(student_ids)
            })

        else:  # researcher or admin
            users_count = User.objects.count()
            courses_count = Course.objects.count()
            payments_total = Payment.objects.filter(status=Payment.SUCCESS).aggregate(total=Sum('amount'))['total'] or 0
            data.update({'users_count': users_count, 'courses_count': courses_count, 'payments_total': float(payments_total)})

        return Response(data)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class UserAdminViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Admin user listing / detail / delete endpoints for master admin with search, filter and pagination."""
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserSerializer
    permission_classes = [IsMasterAdmin]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['id', 'username', 'email']


class ChangePasswordView(APIView):
    """Endpoint to change user password."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        # Validate inputs
        if not old_password or not new_password or not confirm_password:
            return Response(
                {'error': 'All fields are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if old password is correct
        if not user.check_password(old_password):
            return Response(
                {'error': 'Old password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if new passwords match
        if new_password != confirm_password:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check password length
        if len(new_password) < 8:
            return Response(
                {'error': 'Password must be at least 8 characters long'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set new password
        user.set_password(new_password)
        user.save()

        return Response(
            {'message': 'Password changed successfully'},
            status=status.HTTP_200_OK
        )


class ProfileUpdateView(APIView):
    """Endpoint to update user profile information."""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request):
        user = request.user
        
        # Get fields from request
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')

        # Validate email uniqueness if changed
        if email and email != user.email:
            if User.objects.filter(email=email).exists():
                return Response(
                    {'error': 'Email already in use'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.email = email

        # Update fields
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name

        user.save()

        return Response(
            {
                'message': 'Profile updated successfully',
                'user': UserSerializer(user).data
            },
            status=status.HTTP_200_OK
        )