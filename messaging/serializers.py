from rest_framework import serializers
from .models import Message, DirectMessage


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


class DirectMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    sender_id = serializers.IntegerField(source='sender.id', read_only=True)
    recipient_username = serializers.CharField(source='recipient.username', read_only=True)
    recipient_id = serializers.IntegerField(source='recipient.id', read_only=True)

    class Meta:
        model = DirectMessage
        fields = [
            'id', 'thread_id', 'sender', 'sender_id', 'sender_username',
            'recipient', 'recipient_id', 'recipient_username', 'message',
            'is_read', 'read_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'thread_id', 'sender', 'sender_id', 'sender_username',
            'recipient_id', 'recipient_username', 'is_read', 'read_at', 'created_at', 'updated_at'
        ]


class DirectMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for sending direct messages."""
    recipient_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = DirectMessage
        fields = ['recipient_id', 'message']

    def create(self, validated_data):
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        
        User = get_user_model()
        sender = self.context['request'].user
        recipient_id = validated_data.pop('recipient_id')
        
        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            raise serializers.ValidationError(f'User with ID {recipient_id} not found')
        
        # Create thread_id for conversation (normalize so admin + user always have same thread)
        ids = sorted([sender.id, recipient.id])
        thread_id = f'direct_{ids[0]}_{ids[1]}'
        
        direct_message = DirectMessage.objects.create(
            thread_id=thread_id,
            sender=sender,
            recipient=recipient,
            message=validated_data['message']
        )
        
        return direct_message


class DirectMessageThreadSerializer(serializers.ModelSerializer):
    """Serializer for listing conversations/threads."""
    other_user_id = serializers.SerializerMethodField()
    other_user_username = serializers.SerializerMethodField()
    other_user_first_name = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_date = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = DirectMessage
        fields = [
            'thread_id', 'other_user_id', 'other_user_username',
            'other_user_first_name', 'last_message', 'last_message_date', 'unread_count'
        ]

    def get_other_user_id(self, obj):
        """Get the ID of the other user in this thread."""
        current_user = self.context['request'].user
        return obj.sender.id if obj.recipient.id == current_user.id else obj.recipient.id

    def get_other_user_username(self, obj):
        """Get the username of the other user."""
        current_user = self.context['request'].user
        other_user = obj.sender if obj.recipient.id == current_user.id else obj.recipient
        return other_user.username

    def get_other_user_first_name(self, obj):
        """Get the first name of the other user."""
        current_user = self.context['request'].user
        other_user = obj.sender if obj.recipient.id == current_user.id else obj.recipient
        return other_user.first_name

    def get_last_message(self, obj):
        """Get the last message in the thread."""
        last_msg = DirectMessage.objects.filter(thread_id=obj.thread_id).order_by('-created_at').first()
        return last_msg.message if last_msg else ''

    def get_last_message_date(self, obj):
        """Get the date of the last message."""
        last_msg = DirectMessage.objects.filter(thread_id=obj.thread_id).order_by('-created_at').first()
        return last_msg.created_at if last_msg else None

    def get_unread_count(self, obj):
        """Count unread messages from other user in this thread."""
        current_user = self.context['request'].user
        return DirectMessage.objects.filter(
            thread_id=obj.thread_id,
            recipient=current_user,
            is_read=False
        ).count()
