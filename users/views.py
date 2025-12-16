from rest_framework import generics, permissions
from rest_framework.response import Response
from .models import User
from .serializers import UserSerializer, RegisterSerializer
from rest_framework.views import APIView
from rest_framework import viewsets, mixins
from rest_framework import permissions as drf_permissions
from rest_framework import filters
from rest_framework.pagination import PageNumberPagination
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
            inst_qs = user.owned_institutions.all()
            inst_count = inst_qs.count()
            courses_count = Course.objects.filter(institution__in=inst_qs).count()
            students_count = User.objects.filter(institution_name__in=[i.name for i in inst_qs]).count()
            data.update({'institutions_count': inst_count, 'courses_count': courses_count, 'students_count': students_count})

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
