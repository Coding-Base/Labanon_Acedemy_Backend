from rest_framework import serializers
from .models import PromoCode


class PromoCodeSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = PromoCode
        fields = ['id', 'code', 'amount', 'is_percentage', 'max_uses', 'uses', 'expires_at', 'active', 'applicable_to', 'created_by', 'created_by_username', 'created_at', 'updated_at']
        read_only_fields = ['uses', 'created_at', 'updated_at', 'created_by']
