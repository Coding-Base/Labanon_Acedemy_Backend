from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class ProPlan(models.Model):
    """Admin-configured Pro subscription tier."""
    name = models.CharField(max_length=100, help_text="e.g. Pro Monthly, Pro Exam Master")
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True, help_text="Brief marketing summary of this plan")
    price_ngn = models.DecimalField(max_digits=10, decimal_places=2, default=3500.00, help_text="Price in NGN")
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, default=5.00, help_text="Price in USD")
    billing_interval_days = models.PositiveIntegerField(default=30, help_text="Duration of subscription in days (e.g. 30 for monthly, 365 for annual)")
    
    # Feature / Access permissions
    all_exams_unlocked = models.BooleanField(default=True, help_text="Grants access to ALL CBT exams without individual activation")
    included_exams = models.ManyToManyField('cbt.Exam', blank=True, related_name='pro_plans', help_text="Specific exams included if all_exams_unlocked is False")
    allow_mock_exams = models.BooleanField(default=True, help_text="Grants access to custom mock exams")
    allow_materials_download = models.BooleanField(default=True, help_text="Grants download of past questions & study materials")
    material_download_limit = models.PositiveIntegerField(default=0, help_text="0 for unlimited, or specific max downloads allowed per billing cycle")
    
    # Marketing perks list stored as JSON or newline-separated strings
    features_list = models.JSONField(default=list, blank=True, help_text="List of feature bullet points for checkout card")
    badge = models.CharField(max_length=50, blank=True, null=True, help_text="Marketing tag e.g. 'Most Popular', 'Best Value'")
    is_active = models.BooleanField(default=True, help_text="Whether this tier is visible and purchasable by students")
    order = models.PositiveIntegerField(default=0, help_text="Display order in pricing tables")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'price_ngn']
        verbose_name = 'Pro Plan'
        verbose_name_plural = 'Pro Plans'

    def __str__(self):
        return f"{self.name} (₦{self.price_ngn:,.2f} / ${self.price_usd:,.2f})"


class UserSubscription(models.Model):
    """Represents a student's active or past Pro subscription."""
    STATUS_ACTIVE = 'active'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'
    STATUS_PENDING = 'pending'
    
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_PENDING, 'Pending'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(ProPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(help_text="When this subscription expires")
    auto_renew = models.BooleanField(default=True, help_text="Whether to auto-renew card charge on expiry")
    
    # Paystack recurring token metadata
    paystack_customer_code = models.CharField(max_length=255, blank=True, null=True)
    paystack_authorization_code = models.CharField(max_length=255, blank=True, null=True, help_text="Saved card authorization token for recurring debits")
    paystack_subscription_code = models.CharField(max_length=255, blank=True, null=True)
    card_last4 = models.CharField(max_length=8, blank=True, null=True, help_text="Last 4 digits of saved card")
    card_brand = models.CharField(max_length=32, blank=True, null=True, help_text="e.g. Visa, Mastercard, Verve")
    
    last_payment = models.ForeignKey('courses.Payment', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    notes = models.TextField(blank=True, null=True, help_text="Admin or system notes")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['end_date', 'status']),
        ]

    def is_valid(self):
        """Check if subscription is currently active and unexpired."""
        if self.status == self.STATUS_ACTIVE and self.end_date > timezone.now():
            return True
        return False

    def days_remaining(self):
        """Calculates number of days left before expiration."""
        if self.end_date <= timezone.now():
            return 0
        delta = self.end_date - timezone.now()
        return max(0, delta.days)

    def __str__(self):
        plan_name = self.plan.name if self.plan else "Custom Pro"
        return f"{self.user.username} - {plan_name} ({self.status})"


class SubscriptionResetLog(models.Model):
    """Audit log of master admin bulk reset actions for exam subscriptions."""
    admin_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='subscription_resets')
    exam_identifier = models.CharField(max_length=255, default='all', help_text="Exam slug/id reset or 'all'")
    exam_title = models.CharField(max_length=255, default='All Exams')
    months_threshold = models.PositiveIntegerField(help_text="Cutoff duration in months (e.g. 9)")
    cutoff_date = models.DateTimeField(help_text="Calculated date before which unlocks were revoked")
    affected_users_count = models.PositiveIntegerField(default=0, help_text="Number of student unlocks reset")
    reason = models.TextField(blank=True, default="Scheduled periodic subscription reset")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Reset {self.exam_title} (> {self.months_threshold} mos) on {self.created_at.strftime('%Y-%m-%d')} - {self.affected_users_count} users"
