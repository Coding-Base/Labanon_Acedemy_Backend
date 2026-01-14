from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth import get_user_model
from .models import Message
from .serializers import MessageSerializer, MessageCreateSerializer, MessageReplySerializer
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.core.mail import send_mail
from django.conf import settings

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

            # Send an email notification to admin(s) for incoming public messages
            try:
                admin_emails = list(admins.values_list('email', flat=True)) if admins.exists() else []
                admin_email = getattr(settings, 'ADMIN_EMAIL', None)
                if admin_email and admin_email not in admin_emails:
                    admin_emails.append(admin_email)

                if admin_emails:
                    subject = f"New Contact Message: {validated.get('subject')}"
                    plain = validated.get('message')
                    html = f"<p><strong>From:</strong> {sender.username} ({sender.email})</p><p><strong>Type:</strong> {validated.get('message_type')}</p><p>{validated.get('message')}</p>"
                    send_mail(subject=subject, message=plain, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=admin_emails, html_message=html, fail_silently=True)
            except Exception:
                pass

            return Response(out.data, status=status.HTTP_201_CREATED)

        # If recipient was provided, use serializer.save() to create single message
        instance = serializer.save()
        out = MessageSerializer(instance, context={'request': request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class ContactAPIView(APIView):
    """Public contact endpoint for unauthenticated users to reach admin."""
    permission_classes = [AllowAny]
    # Skip authentication so public users (no token) can post without triggering
    # JWT authentication errors (e.g. expired token). Permissions run after
    # authentication; by clearing authentication_classes we ensure AllowAny
    # requests are accepted.
    authentication_classes = []

    def post(self, request):
        data = request.data
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        subject = data.get('subject') or f'Contact from website ({data.get("type")})'
        message = data.get('message')
        message_type = data.get('type') or 'contact'

        if not name or not email or not message:
            return Response({'detail': 'name, email and message are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Build email
        admin_email = getattr(settings, 'ADMIN_EMAIL', None)
        recipients = [admin_email] if admin_email else []

        if not recipients:
            return Response({'detail': 'No admin email configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        html = f"""
            <p><strong>From:</strong> {name} &lt;{email}&gt;</p>
            <p><strong>Phone:</strong> {phone or 'N/A'}</p>
            <p><strong>Type:</strong> {message_type}</p>
            <hr/>
            <p>{message}</p>
        """

        try:
            send_mail(subject=subject, message=message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=recipients, html_message=html, fail_silently=True)
        except Exception:
            pass

        # Optionally persist in Message table using master admin as sender so admins see it in inbox
        try:
            User = get_user_model()
            master_admin = User.objects.filter(is_superuser=True).first()
            if master_admin:
                # create Message entries for each admin recipient
                for r in recipients:
                    admin_user = User.objects.filter(email=r).first()
                    if admin_user:
                        Message.objects.create(
                            sender=master_admin,
                            recipient=admin_user,
                            subject=subject,
                            message=f"From: {name} <{email}>\nPhone: {phone or ''}\n\n{message}",
                            message_type=Message.MESSAGE_TYPE_CONTACT,
                        )
        except Exception:
            pass

        return Response({'status': 'ok'}, status=status.HTTP_201_CREATED)

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