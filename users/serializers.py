from rest_framework import serializers
from django.core.validators import RegexValidator
from django.conf import settings
from django.db import models
from django.db.models import Sum, Avg
from .models import User, InstitutionProfile
from .models import TrialConfig, Review
import uuid

# Safe import for Djoser to prevent Pylance/Runtime errors if not installed
try:
    from djoser.serializers import UserCreateSerializer as DjoserBaseUserCreateSerializer
except ImportError:
    # Fallback to standard ModelSerializer if djoser is missing
    from rest_framework.serializers import ModelSerializer as DjoserBaseUserCreateSerializer


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # include date_joined so frontend can determine trial window
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'institution_name', 'is_unlocked', 'date_joined']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    admin_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Allow spaces in username in addition to the default set of allowed characters
    username = serializers.CharField(
        required=True,
        validators=[
            RegexValidator(
                regex=r'^[\w.@+\- ]+$',
                message="Enter a valid username. This value may contain only letters, numbers, spaces and @/./+/-/_ characters."
            )
        ]
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role', 'institution_name', 'admin_secret']

    def validate_email(self, value):
        """Ensure email is not already used (verified or unverified)"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "This email is already registered. Please use a different email or reset your password if you forgot it."
            )
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        role = validated_data.get('role')
        admin_secret = validated_data.pop('admin_secret', '')
        
        # Prevent anonymous or non-admin users from registering as 'admin'
        if role == User.ADMIN:
            request = self.context.get('request')
            user_request = getattr(request, 'user', None)
            
            # allow if requester is already an authenticated admin
            is_admin_request = user_request and user_request.is_authenticated and getattr(user_request, 'role', None) == User.ADMIN
            
            # or allow if a server-side invite code is provided and matches
            invite_code = getattr(settings, 'ADMIN_INVITE_CODE', None)
            is_valid_invite = invite_code and admin_secret == invite_code

            if not (is_admin_request or is_valid_invite):
                raise serializers.ValidationError({'role': 'Cannot register as admin.'})

        # 1. Create the User with email verification token
        user = User(**validated_data)
        user.set_password(password)
        user.email_verified = False
        user.email_verification_token = str(uuid.uuid4())
        user.save()

        # If account was created as an Admin (and validation allowed it), set staff/superuser flags
        try:
            if role == User.ADMIN:
                user.is_staff = True
                user.is_superuser = True
                user.save()
        except Exception:
            pass

        # 2. AUTOMATICALLY CREATE INSTITUTION & PORTFOLIO
        if role == User.INSTITUTION:
            try:
                # Local import to avoid circular dependency (User -> Course -> User)
                from courses.models import Institution, Portfolio
                from .models import InstitutionProfile
                
                # Get name from input or default to Username
                inst_name = validated_data.get('institution_name')
                if not inst_name:
                    inst_name = f"{user.username}'s Institution"
                
                # Create Institution Record
                institution = Institution.objects.create(
                    owner=user,
                    name=inst_name,
                    description=f"Welcome to {inst_name}. We provide top-tier educational services."
                )
                
                # Create Portfolio Record
                Portfolio.objects.create(
                    institution=institution,
                    title=inst_name,
                    public_token=str(uuid.uuid4()), # Generate unique public link
                    published=False # Default to draft
                )
                
                # Create InstitutionProfile Record for detailed profile data
                InstitutionProfile.objects.create(
                    user=user,
                    full_name=validated_data.get('full_name', ''),
                    job_title=validated_data.get('job_title', ''),
                    work_email=validated_data.get('work_email', user.email),
                    institution_name=inst_name,
                    institution_type=validated_data.get('institution_type', 'tutorial_center'),
                    position=validated_data.get('position', 'others'),
                    department=validated_data.get('department', ''),
                    country=validated_data.get('country', ''),
                    purpose=validated_data.get('purpose', '')
                )
                print(f"Auto-created Institution, Portfolio & InstitutionProfile for {user.username}")
                
            except Exception as e:
                # Log error but allow user creation to succeed (prevents registration crash)
                print(f"CRITICAL ERROR: Failed to auto-create institution profile: {e}")

        return user


class DjoserUserCreateSerializer(DjoserBaseUserCreateSerializer):
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default=User.STUDENT)
    institution_name = serializers.CharField(allow_blank=True, required=False)
    admin_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Override the username field coming from Djoser to permit spaces
    username = serializers.CharField(
        required=True,
        validators=[
            RegexValidator(
                regex=r'^[\w.@+\- ]+$',
                message="Enter a valid username. This value may contain only letters, numbers, spaces and @/./+/-/_ characters."
            )
        ]
    )

    class Meta(DjoserBaseUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'username', 'email', 'password', 'role', 'institution_name', 'admin_secret')

    def validate(self, attrs):
        # Prevent registering as admin unless the requester is an authenticated admin
        request = self.context.get('request')
        role = attrs.get('role')
        admin_secret = attrs.get('admin_secret', '')
        
        if role == User.ADMIN:
            user_request = getattr(request, 'user', None)
            is_admin_request = user_request and user_request.is_authenticated and getattr(user_request, 'role', None) == User.ADMIN
            
            invite_code = getattr(settings, 'ADMIN_INVITE_CODE', None)
            is_valid_invite = invite_code and admin_secret == invite_code

            if not (is_admin_request or is_valid_invite):
                raise serializers.ValidationError({'role': 'Cannot register as admin.'})
        
        # Clean up admin_secret from attrs so it doesn't get passed to create()
        if 'admin_secret' in attrs:
            del attrs['admin_secret']
            
        return super().validate(attrs)

    def create(self, validated_data):
        # Allow Djoser to handle the standard user creation
        user = super().create(validated_data)
        
        # Add email verification fields
        user.email_verified = False
        user.email_verification_token = str(uuid.uuid4())
        user.save()
        
        # Add the same auto-creation logic here in case Djoser endpoint is used
        if user.role == User.INSTITUTION:
            try:
                from courses.models import Institution, Portfolio
                
                inst_name = validated_data.get('institution_name') or f"{user.username}'s Institution"
                
                institution = Institution.objects.create(
                    owner=user,
                    name=inst_name,
                    description=f"Welcome to {inst_name}."
                )
                
                Portfolio.objects.create(
                    institution=institution,
                    title=inst_name,
                    public_token=str(uuid.uuid4()),
                    published=False
                )
            except Exception as e:
                print(f"CRITICAL ERROR (Djoser): Failed to auto-create institution profile: {e}")
        
        # Ensure admin flags are set when role == ADMIN and creation was authorized
        try:
            if user.role == User.ADMIN:
                user.is_staff = True
                user.is_superuser = True
                user.save()
        except Exception:
            pass

        return user


# Serializer for TrialConfig
class TrialConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrialConfig
        fields = ['trial_days']


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'author', 'name', 'role', 'rating', 'message', 'is_approved', 'category', 'cbt_exam', 'cbt_subject', 'cbt_score', 'created_at']
        read_only_fields = ['created_at']

    def get_author(self, obj):
        if obj.author:
            return {'id': obj.author.id, 'username': obj.author.username}
        return None

    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            validated_data['author'] = user
            if not validated_data.get('name'):
                validated_data['name'] = user.get_full_name() or user.username
            if not validated_data.get('role'):
                validated_data['role'] = getattr(user, 'role', 'student')
        # By default, new reviews require admin approval
        validated_data['is_approved'] = False
        return super().create(validated_data)


# Specialized serializers for detailed user information needed by management dashboards

class StudentDetailSerializer(serializers.ModelSerializer):
    """Detailed student information including enrollment and spending data"""
    # `phone` may not be a direct field on the custom User model in all deployments;
    # expose it via a SerializerMethodField to avoid DRF trying to map a non-existent
    # model field (which raises ImproperlyConfigured).
    phone = serializers.SerializerMethodField()
    courses_enrolled = serializers.SerializerMethodField()
    total_spending = serializers.SerializerMethodField()
    certificates_earned = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'username', 'date_joined', 
                  'is_active', 'last_login', 'courses_enrolled', 'total_spending', 'certificates_earned']

    def get_courses_enrolled(self, obj):
        """Count successful course enrollments"""
        from courses.models import Enrollment
        return Enrollment.objects.filter(user=obj, purchased=True).count()

    def get_total_spending(self, obj):
        """Sum all successful payments for this student"""
        from courses.models import Payment
        total = Payment.objects.filter(
            user=obj,
            status=Payment.SUCCESS
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        return float(total)

    def get_certificates_earned(self, obj):
        """Count certificates earned by student"""
        from courses.models import Certificate
        return Certificate.objects.filter(user=obj).count()

    def get_phone(self, obj):
        # Prefer a direct attribute if present, otherwise attempt common fallbacks
        return getattr(obj, 'phone', None)


class TutorDetailSerializer(serializers.ModelSerializer):
    """Detailed tutor information including courses, ratings, and verification status"""
    phone = serializers.SerializerMethodField()
    verification_status = serializers.SerializerMethodField()
    courses_count = serializers.SerializerMethodField()
    students_taught = serializers.SerializerMethodField()
    total_revenue = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'username', 'date_joined',
                  'is_active', 'verification_status', 'courses_count', 'students_taught', 
                  'total_revenue', 'average_rating']

    def get_verification_status(self, obj):
        """Get tutor verification status from TutorVerificationDocument"""
        from courses.models import TutorVerificationDocument
        doc = TutorVerificationDocument.objects.filter(tutor=obj).order_by('-reviewed_at').first()
        return doc.status if doc else 'pending'

    def get_courses_count(self, obj):
        """Count courses created by tutor"""
        from courses.models import Course
        return Course.objects.filter(creator=obj).count()

    def get_students_taught(self, obj):
        """Count unique students enrolled in tutor's courses"""
        from courses.models import Enrollment, Course
        return Enrollment.objects.filter(
            course__creator=obj,
            purchased=True
        ).values('user').distinct().count()

    def get_total_revenue(self, obj):
        """Sum all course sales revenue for tutor"""
        from courses.models import Payment, Course
        total = Payment.objects.filter(
            course__creator=obj,
            status=Payment.SUCCESS
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        return float(total)

    def get_average_rating(self, obj):
        """Calculate average rating from course reviews"""
        # Reviews store the actual rating values; aggregate directly from Review
        from courses.models import Review
        from django.db.models import Avg
        avg_rating = Review.objects.filter(
            course__creator=obj
        ).aggregate(avg_rating=Avg('rating'))['avg_rating']
        return float(avg_rating) if avg_rating else 0.0

    def get_phone(self, obj):
        return getattr(obj, 'phone', None)


class InstitutionDetailSerializer(serializers.ModelSerializer):
    """Detailed institution information including verification and economics"""
    phone = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    verification_status = serializers.SerializerMethodField()
    verified_by_name = serializers.SerializerMethodField()
    custom_share_percentage = serializers.SerializerMethodField()
    courses_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'username', 'institution_name',
                  'date_joined', 'is_active', 'owner_name', 'verification_status', 'verified_by_name', 'custom_share_percentage', 'courses_count']

    def get_owner_name(self, obj):
        """Return institution owner's full name"""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username

    def get_verification_status(self, obj):
        """Get institution verification status"""
        from courses.models import Institution
        try:
            inst = Institution.objects.get(owner=obj)
            return inst.verification_status
        except:
            return 'pending'

    def get_verified_by_name(self, obj):
        """Get name of admin who verified institution"""
        from courses.models import Institution
        try:
            inst = Institution.objects.get(owner=obj)
            if inst.verified_by:
                return f"{inst.verified_by.first_name} {inst.verified_by.last_name}".strip() or inst.verified_by.username
        except:
            pass
        return None

    def get_courses_count(self, obj):
        """Count courses under institution"""
        from courses.models import Course, Institution
        try:
            inst = Institution.objects.get(owner=obj)
            return Course.objects.filter(institution=inst).count()
        except:
            return 0

    def get_custom_share_percentage(self, obj):
        """Return institution custom share percentage if set"""
        try:
            from courses.models import Institution
            inst = Institution.objects.filter(owner=obj).first()
            if inst and inst.custom_share_percentage is not None:
                return float(inst.custom_share_percentage)
        except Exception:
            pass
        return None

    def get_phone(self, obj):
        # Institutions may keep phone on related Institution record; try that first
        try:
            from courses.models import Institution
            inst = Institution.objects.filter(owner=obj).first()
            if inst and getattr(inst, 'phone', None):
                return inst.phone
        except Exception:
            pass
        return getattr(obj, 'phone', None)


class VerificationStatusSerializer(serializers.Serializer):
    """Serializer for user verification status response"""
    role = serializers.CharField()
    is_verified = serializers.BooleanField()
    verification_status = serializers.CharField()  # 'pending', 'approved', 'rejected', 'not_applicable'
    reason = serializers.CharField(required=False, allow_blank=True)
    verified_at = serializers.DateTimeField(required=False, allow_null=True)


class InstitutionProfileSerializer(serializers.ModelSerializer):
    """Serializer for InstitutionProfile with nested data and calculated fields"""
    purpose_list = serializers.SerializerMethodField()
    certifications_list = serializers.SerializerMethodField()
    
    class Meta:
        from .models import InstitutionProfile
        model = InstitutionProfile
        fields = [
            'id', 'user', 'full_name', 'job_title', 'work_email',
            'institution_name', 'institution_type', 'position', 'department', 'country',
            'purpose', 'purpose_list', 'can_create_diploma_courses', 'can_create_degree_programs',
            'can_upload_projects', 'allowed_certifications', 'certifications_list', 'dashboard_variant',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'can_create_diploma_courses', 'can_create_degree_programs', 'can_upload_projects',
            'allowed_certifications', 'dashboard_variant', 'created_at', 'updated_at'
        ]
    
    def get_purpose_list(self, obj):
        """Return purpose as a list of dicts with value and label"""
        from .models import InstitutionProfile
        purpose_map = {choice[0]: choice[1] for choice in InstitutionProfile.PURPOSE_CHOICES}
        return [
            {'value': p.strip(), 'label': purpose_map.get(p.strip(), p.strip())}
            for p in obj.purpose.split(',') if p.strip()
        ]
    
    def get_certifications_list(self, obj):
        """Return certifications as a list"""
        return obj.get_certifications_list()


class RegisterWithInstitutionProfileSerializer(serializers.Serializer):
    """Enhanced registration serializer that handles institution profile data"""
    # Standard user fields
    username = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default=User.STUDENT)
    
    # Institution-specific fields (only required if role == 'institution')
    institution_name = serializers.CharField(required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True)
    job_title = serializers.CharField(required=False, allow_blank=True)
    work_email = serializers.EmailField(required=False, allow_blank=True)
    institution_type = serializers.CharField(required=False, allow_blank=True)
    position = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)
    purpose = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, attrs):
        """Validate that institution fields are provided if role is institution"""
        role = attrs.get('role')
        
        if role == User.INSTITUTION:
            required_fields = ['institution_name', 'institution_type', 'position', 'department', 'country']
            for field in required_fields:
                if not attrs.get(field):
                    raise serializers.ValidationError({field: f"{field} is required for institution accounts"})
        
        return attrs
    
    def create(self, validated_data):
        """Create user and institution profile"""
        from .models import InstitutionProfile
        
        # Extract institution fields
        institution_fields = {
            'full_name': validated_data.pop('full_name', ''),
            'job_title': validated_data.pop('job_title', ''),
            'work_email': validated_data.pop('work_email', ''),
            'institution_name': validated_data.pop('institution_name', ''),
            'institution_type': validated_data.pop('institution_type', ''),
            'position': validated_data.pop('position', ''),
            'department': validated_data.pop('department', ''),
            'country': validated_data.pop('country', ''),
            'purpose': validated_data.pop('purpose', ''),
        }
        
        password = validated_data.pop('password')
        role = validated_data.get('role')
        
        # Create user
        user = User(**validated_data)
        user.set_password(password)
        # Mark email as unverified initially
        user.email_verified = False
        user.email_verification_token = str(uuid.uuid4())
        user.save()
        
        # Create institution profile if role is institution
        if role == User.INSTITUTION:
            InstitutionProfile.objects.create(
                user=user,
                **{k: v for k, v in institution_fields.items() if v}
            )
            
            # Also auto-create Institution and Portfolio (existing logic)
            try:
                from courses.models import Institution, Portfolio
                inst_name = institution_fields.get('institution_name', f"{user.username}'s Institution")
                
                institution = Institution.objects.create(
                    owner=user,
                    name=inst_name,
                    description=f"Welcome to {inst_name}."
                )
                
                Portfolio.objects.create(
                    institution=institution,
                    title=inst_name,
                    public_token=str(uuid.uuid4()),
                    published=False
                )
            except Exception as e:
                print(f"Warning: Failed to auto-create institution: {e}")
        
        return user


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification"""
    token = serializers.CharField(required=True)
    
    def validate_token(self, value):
        """Validate that the token exists and hasn't expired"""
        try:
            user = User.objects.get(email_verification_token=value, email_verified=False)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired verification token")
        return value
    
    def save(self):
        """Mark user's email as verified"""
        from django.utils import timezone
        token = self.validated_data.get('token')
        user = User.objects.get(email_verification_token=token)
        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.email_verification_token = None
        user.save()
        return user


class ResendVerificationEmailSerializer(serializers.Serializer):
    """Serializer for resending verification email"""
    email = serializers.EmailField(
        error_messages={
            'required': 'Email address is required.',
            'invalid': 'Please enter a valid email address.',
        }
    )
    
    def validate_email(self, value):
        """Check if email exists and is unverified"""
        # Check if any unverified user with this email exists
        unverified_users = User.objects.filter(email=value, email_verified=False)
        
        if not unverified_users.exists():
            raise serializers.ValidationError(
                "No unverified account found with this email. It may already be verified or doesn't exist. "
                "Please register a new account or check a different email."
            )
        
        # If multiple unverified accounts exist, warn the user
        if unverified_users.count() > 1:
            raise serializers.ValidationError(
                "Multiple unverified accounts found with this email. Please contact support for assistance."
            )
        
        return value