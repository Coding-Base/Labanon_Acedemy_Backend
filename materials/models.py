# backend/materials/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum
import uuid


class Material(models.Model):
    """
    Digital materials/documents created by admin that can be bought or downloaded.
    All revenue goes to the platform (no creator split).
    """
    
    AREAS = [
        ('academy', 'Academy'),
        ('research', 'Research'),
        ('interview', 'Interview Prep'),
        ('science', 'Science'),
        ('art', 'Art'),
        ('discovery', 'Discovery'),
        ('invention', 'Invention'),
        ('project', 'Project'),
        ('other', 'Other'),
    ]
    
    FILE_SOURCES = [
        ('upload', 'Direct Upload'),
        ('gdrive', 'Google Drive Link'),
    ]
    
    # Core fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Name/title of the material")
    description = models.TextField(blank=True, help_text="Brief description of the material")
    area = models.CharField(
        max_length=50, 
        choices=AREAS,
        help_text="Category area (e.g., Academy, Research, Science)"
    )
    creator_name = models.CharField(
        max_length=255,
        help_text="Name to display as creator (typically author name)"
    )
    licenses = models.CharField(
        max_length=255,
        help_text="License type (e.g., CC-BY-4.0, MIT, All Rights Reserved)"
    )
    topic_category = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Topic for search/filter (e.g., Maths, Physics, Biology)"
    )
    
    # File storage options
    file_source = models.CharField(
        max_length=20,
        choices=FILE_SOURCES,
        help_text="Type of file storage"
    )
    file_url = models.URLField(
        blank=True,
        null=True,
        help_text="S3/CloudFront signed URL for direct uploads"
    )
    gdrive_link = models.URLField(
        blank=True,
        null=True,
        help_text="Google Drive sharing link"
    )
    file_size = models.BigIntegerField(
        help_text="File size in bytes"
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Original filename for reference"
    )
    image_url = models.URLField(
        blank=True,
        null=True,
        help_text="Optional thumbnail/cover image URL for the material"
    )
    image_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Original image filename"
    )
    
    # Pricing (ALL revenue to platform/admin, no split)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Price in local currency. 0 = FREE"
    )
    currency = models.CharField(
        max_length=3,
        default='NGN',
        help_text="ISO 4217 currency code"
    )
    
    # Total statistics
    total_revenue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Total revenue from all purchases"
    )
    
    # Admin tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='materials_created',
        help_text="Admin who created this material"
    )
    is_published = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Is material visible in marketplace"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_published', '-created_at']),
            models.Index(fields=['topic_category']),
            models.Index(fields=['area']),
        ]
        permissions = [
            ('can_manage_materials', 'Can create, edit, delete materials'),
        ]
    
    def __str__(self):
        return self.name
    
    @property
    def is_free(self):
        """Check if material is free."""
        return self.price == 0
    
    @property
    def total_downloads(self):
        """Get total download count across all purchases."""
        return self.purchases.aggregate(
            total=Sum('download_count')
        )['total'] or 0
    
    @property
    def total_purchases(self):
        """Get total number of unique purchases."""
        return self.purchases.count()


class MaterialPurchase(models.Model):
    """
    Tracks which users have access to a material (either free or paid).
    Foreign Key to Payment only for paid materials (NULL for free).
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='material_purchases'
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='purchases'
    )
    
    # Payment (only for paid materials, NULL for free)
    payment = models.OneToOneField(
        'courses.Payment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_purchase',
        help_text="Payment record if material was purchased (NULL if free)"
    )
    
    # Access tracking
    accessed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When user first got access"
    )
    download_count = models.IntegerField(
        default=0,
        help_text="How many times user downloaded this material"
    )
    last_downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When user last downloaded"
    )
    
    class Meta:
        unique_together = ['user', 'material']
        ordering = ['-accessed_at']
        indexes = [
            models.Index(fields=['user', '-accessed_at']),
            models.Index(fields=['material', '-accessed_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} → {self.material.name}"


class MaterialDownload(models.Model):
    """
    Records individual download events with expiring download links.
    Tracks when user requests download, generates signed URL, sends email.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='material_downloads'
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='download_records'
    )
    
    # Expiring link tracking
    download_token = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique token for tracking"
    )
    link_expires_at = models.DateTimeField(
        help_text="When the download link expires"
    )
    downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When user actually clicked/downloaded"
    )
    
    # User metadata
    ip_address = models.CharField(
        max_length=45,
        blank=True,
        help_text="User's IP address"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Browser user agent"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['download_token']),
        ]
    
    def __str__(self):
        return f"Download {self.user.email} → {self.material.name} (expires: {self.link_expires_at})"
    
    @property
    def is_expired(self):
        """Check if download link has expired."""
        return timezone.now() > self.link_expires_at
