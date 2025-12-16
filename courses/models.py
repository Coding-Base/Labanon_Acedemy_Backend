from django.db import models
from django.conf import settings


class Institution(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_institutions')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Course(models.Model):
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='courses')
    institution = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    image = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Lesson(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    video = models.CharField(max_length=512, blank=True)  # store Cloudinary public id or remote URL
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.module.title} - {self.title}"


class Enrollment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    purchased = models.BooleanField(default=False)
    purchased_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user} -> {self.course}"


class Payment(models.Model):
    PENDING = 'pending'
    SUCCESS = 'success'
    FAILED = 'failed'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (SUCCESS, 'Success'),
        (FAILED, 'Failed'),
    ]

    KIND_COURSE = 'course'
    KIND_UNLOCK = 'unlock'

    KIND_CHOICES = [
        (KIND_COURSE, 'Course Purchase'),
        (KIND_UNLOCK, 'Account Unlock'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_COURSE)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    provider_reference = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.id} {self.user} {self.course} {self.amount} {self.status}"


class CartItem(models.Model):
    """Simple cart item representing a course added to a user's cart."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart_items')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='cart_items')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"CartItem {self.user} -> {self.course}"
