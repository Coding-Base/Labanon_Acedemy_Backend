from rest_framework import serializers
from .models import Message


class MessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    sender_email = serializers.CharField(source='sender.email', read_only=True)
    recipient_username = serializers.CharField(source='recipient.username', read_only=True)

    class Meta:
        model = Message
        fields = [
            'id', 'sender', 'sender_username', 'sender_email', 
            'recipient', 'recipient_username', 'subject', 'message', 
            'message_type', 'is_read', 'is_replied', 'reply_message', 
            'replied_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'sender_username', 'sender_email', 'recipient_username', 'created_at', 'updated_at']


class MessageCreateSerializer(serializers.ModelSerializer):
    recipient = serializers.IntegerField(required=False, allow_null=True)
    
    class Meta:
        model = Message
        fields = ['recipient', 'subject', 'message', 'message_type']

    def create(self, validated_data):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        validated_data['sender'] = self.context['request'].user
        
        # Handle recipient - either use provided ID or get master admin
        recipient_id = validated_data.get('recipient')
        
        if recipient_id:
            # Recipient ID was provided, fetch the User object
            try:
                recipient_user = User.objects.get(id=recipient_id)
                validated_data['recipient'] = recipient_user
            except User.DoesNotExist:
                raise serializers.ValidationError(f'User with ID {recipient_id} not found')
        else:
            # No recipient specified, set to master admin (first superuser)
            master_admin = User.objects.filter(is_superuser=True).first()
            if master_admin:
                validated_data['recipient'] = master_admin
            else:
                raise serializers.ValidationError('No master admin found in system')
        
        return super().create(validated_data)


class MessageReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['reply_message']

    def update(self, instance, validated_data):
        from django.utils import timezone
        instance.reply_message = validated_data.get('reply_message', instance.reply_message)
        instance.is_replied = True
        instance.replied_at = timezone.now()
        instance.save()
        return instance
