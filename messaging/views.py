from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth import get_user_model
from .models import Message
from .serializers import MessageSerializer, MessageCreateSerializer, MessageReplySerializer

User = get_user_model()

class MessageViewSet(viewsets.ModelViewSet):
    """Viewset for managing messages between users and admins."""
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Return messages where user is sender or recipient.
        If user is a Sub-Admin with permission, also return Master Admin's messages.
        """
        user = self.request.user
        
        # Base query: messages where I am sender or recipient
        query = Q(sender=user) | Q(recipient=user)

        # Sub-Admin Logic: Include Master Admin's messages if allowed
        if hasattr(user, 'subadmin_profile') and user.subadmin_profile.can_view_messages:
            master_admin = user.subadmin_profile.created_by
            query |= Q(sender=master_admin) | Q(recipient=master_admin)

        return Message.objects.filter(query).order_by('-created_at')

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
        
        validated = serializer.validated_data
        sender = request.user
        recipient_id = validated.get('recipient') if isinstance(validated, dict) else None

        # If recipient not provided, broadcast the message to all users with role='admin'
        if not recipient_id:
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
        """
        Get all messages where user is recipient OR user is sender with a reply.
        Sub-Admins see Master Admin's inbox.
        """
        user = request.user
        
        # 1. Determine whose inbox we are looking at
        recipients = [user]
        if hasattr(user, 'subadmin_profile') and user.subadmin_profile.can_view_messages:
            recipients.append(user.subadmin_profile.created_by)

        # 2. Fetch Messages
        # Messages where (User/Master) is recipient
        recipient_messages = Message.objects.filter(recipient__in=recipients)
        
        # Messages sent by (User/Master) that got replies (to show admin's reply in inbox view)
        replied_messages = Message.objects.filter(sender__in=recipients, is_replied=True)
        
        # 3. Combine and order
        all_messages = (recipient_messages | replied_messages).distinct().order_by('-created_at')
        
        # 4. Pagination
        page = self.paginate_queryset(all_messages)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(all_messages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def sent(self, request):
        """
        Get all messages where user is sender (outgoing messages).
        Sub-Admins see Master Admin's sent items.
        """
        user = request.user
        
        # Determine whose sent items to show
        senders = [user]
        if hasattr(user, 'subadmin_profile') and user.subadmin_profile.can_view_messages:
            senders.append(user.subadmin_profile.created_by)

        messages = Message.objects.filter(sender__in=senders).order_by('-created_at')
        
        page = self.paginate_queryset(messages)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """
        Get count of unread messages.
        Sub-Admins count Master Admin's unread messages too.
        """
        user = request.user
        recipients = [user]
        
        if hasattr(user, 'subadmin_profile') and user.subadmin_profile.can_view_messages:
            recipients.append(user.subadmin_profile.created_by)

        count = Message.objects.filter(recipient__in=recipients, is_read=False).count()
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a message as read."""
        message = self.get_object()
        user = request.user

        # Allow if user is recipient OR user is authorized sub-admin of recipient
        is_recipient = message.recipient == user
        is_authorized_sub = (
            hasattr(user, 'subadmin_profile') and 
            user.subadmin_profile.can_view_messages and 
            message.recipient == user.subadmin_profile.created_by
        )

        if not (is_recipient or is_authorized_sub):
            return Response(
                {'detail': 'You can only mark your own messages as read.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        message.mark_as_read()
        return Response({'status': 'message marked as read'})

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        """Reply to a message (only admin or authorized sub-admin can reply)."""
        message = self.get_object()
        user = request.user

        # Check permissions
        is_admin = user.is_staff or user.role == 'admin'
        is_authorized_sub = (
            hasattr(user, 'subadmin_profile') and 
            user.subadmin_profile.can_view_messages
        )

        if not (is_admin or is_authorized_sub):
            return Response(
                {'detail': 'Only admins can reply to messages.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(message, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)