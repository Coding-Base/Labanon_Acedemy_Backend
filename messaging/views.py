from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import Message
from .serializers import MessageSerializer, MessageCreateSerializer, MessageReplySerializer


class MessageViewSet(viewsets.ModelViewSet):
    """Viewset for managing messages between users and admins."""
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return messages where user is sender or recipient."""
        user = self.request.user
        return Message.objects.filter(Q(sender=user) | Q(recipient=user)).order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return MessageCreateSerializer
        elif self.action == 'reply':
            return MessageReplySerializer
        return MessageSerializer

    def create(self, request, *args, **kwargs):
        """Create a new message."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # If recipient not provided, broadcast the message to all users with role='admin'
        validated = serializer.validated_data
        sender = request.user
        recipient_id = validated.get('recipient') if isinstance(validated, dict) else None

        if not recipient_id:
            # create a message for each admin user
            from django.contrib.auth import get_user_model
            User = get_user_model()
            admins = User.objects.filter(role='admin')
            # fallback to superusers if no role-based admins exist
            if not admins.exists():
                admins = User.objects.filter(is_superuser=True)

            created = []
            for admin in admins:
                msg = Message.objects.create(
                    sender=sender,
                    recipient=admin,
                    subject=validated.get('subject'),
                    message=validated.get('message'),
                    message_type=validated.get('message_type'),
                )
                created.append(msg)

            out = MessageSerializer(created, many=True, context={'request': request})
            return Response(out.data, status=status.HTTP_201_CREATED)

        # If recipient was provided, use serializer.save() to create single message
        instance = serializer.save()
        out = MessageSerializer(instance, context={'request': request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def inbox(self, request):
        """Get all messages where user is recipient OR user is sender with a reply."""
        # Messages where user is recipient (incoming from admins)
        recipient_messages = self.get_queryset().filter(recipient=request.user)
        # Messages sent by user that got replies (to show admin's reply)
        replied_messages = self.get_queryset().filter(sender=request.user, is_replied=True)
        
        # Combine and order by created_at
        all_messages = (recipient_messages | replied_messages).distinct().order_by('-created_at')
        serializer = self.get_serializer(all_messages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def sent(self, request):
        """Get all messages where user is sender (outgoing messages)."""
        messages = self.get_queryset().filter(sender=request.user)
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread messages for current user."""
        count = Message.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a message as read."""
        message = self.get_object()
        if message.recipient != request.user:
            return Response(
                {'detail': 'You can only mark your own messages as read.'},
                status=status.HTTP_403_FORBIDDEN
            )
        message.mark_as_read()
        return Response({'status': 'message marked as read'})

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        """Reply to a message (only admin can reply)."""
        message = self.get_object()
        if not request.user.is_staff and request.user.role != 'admin':
            return Response(
                {'detail': 'Only admins can reply to messages.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(message, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
