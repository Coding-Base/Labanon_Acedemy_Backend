# backend/materials/serializers.py

from rest_framework import serializers
from .models import Material, MaterialPurchase, MaterialDownload


class MaterialListSerializer(serializers.ModelSerializer):
    """Serializer for listing materials in marketplace."""
    
    user_has_access = serializers.SerializerMethodField()
    is_free = serializers.SerializerMethodField()
    total_downloads = serializers.SerializerMethodField()
    total_purchases = serializers.SerializerMethodField()
    
    class Meta:
        model = Material
        fields = [
            'id', 'name', 'description', 'area', 'creator_name', 'licenses',
            'topic_category', 'price', 'currency', 'file_source', 'file_size', 'image_url',
            'is_published', 'created_at', 'updated_at',
            'user_has_access', 'is_free', 'total_downloads', 'total_purchases'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'file_source',
            'user_has_access', 'is_free', 'total_downloads', 'total_purchases'
        ]
    
    def get_user_has_access(self, obj):
        """Check if current user has access to this material."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        
        if obj.is_free:
            return True
        
        # Check if user has purchased
        return obj.purchases.filter(user=request.user).exists()
    
    def get_is_free(self, obj):
        return obj.is_free
    
    def get_total_downloads(self, obj):
        return obj.total_downloads
    
    def get_total_purchases(self, obj):
        return obj.total_purchases


class MaterialDetailSerializer(MaterialListSerializer):
    """Extended serializer for detail view - includes all stats."""
    
    class Meta(MaterialListSerializer.Meta):
        pass


class MaterialCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating materials (admin only)."""
    
    file_name = serializers.CharField(read_only=True)
    total_revenue = serializers.DecimalField(read_only=True, max_digits=15, decimal_places=2)
    file_size = serializers.IntegerField(required=False, default=0)
    file_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    gdrive_link = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    image_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    image_name = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = Material
        fields = [
            'id', 'name', 'description', 'area', 'creator_name', 'licenses',
            'topic_category', 'file_source', 'file_url', 'gdrive_link', 
            'file_size', 'file_name', 'image_url', 'image_name', 'price', 'currency', 'is_published',
            'created_at', 'updated_at', 'total_revenue'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'file_name', 'total_revenue'
        ]
    
    def validate(self, data):
        """Ensure either file_url or gdrive_link is provided."""
        file_source = data.get('file_source')
        file_url = data.get('file_url')
        gdrive_link = data.get('gdrive_link')
        
        # Set default file_size if not provided
        if 'file_size' not in data or data['file_size'] is None:
            data['file_size'] = 0
        
        if file_source == 'upload' and not file_url:
            raise serializers.ValidationError(
                "Direct upload requires file_url (from S3)"
            )
        
        if file_source == 'gdrive' and not gdrive_link:
            raise serializers.ValidationError(
                "Google Drive option requires gdrive_link"
            )
        
        return data


class MaterialPurchaseSerializer(serializers.ModelSerializer):
    """Serializer for user's material purchases."""
    
    material = MaterialListSerializer(read_only=True)
    
    class Meta:
        model = MaterialPurchase
        fields = [
            'id', 'material', 'accessed_at', 'download_count', 
            'last_downloaded_at', 'payment'
        ]
        read_only_fields = fields


class MaterialDownloadSerializer(serializers.ModelSerializer):
    """Serializer for download records."""
    
    class Meta:
        model = MaterialDownload
        fields = [
            'id', 'download_token', 'link_expires_at', 
            'downloaded_at', 'created_at'
        ]
        read_only_fields = fields


class MaterialStatsSerializer(serializers.Serializer):
    """Serializer for material statistics."""
    
    total_materials = serializers.IntegerField()
    total_downloads = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    this_month_growth = serializers.IntegerField()


class DownloadActivitySerializer(serializers.Serializer):
    """Serializer for recent download/payment activities."""
    
    TYPE_CHOICES = [
        ('download', 'Download'),
        ('purchase', 'Purchase'),
    ]
    
    type = serializers.CharField()
    user_email = serializers.CharField()
    material_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    time_ago = serializers.CharField()
    created_at = serializers.DateTimeField()
