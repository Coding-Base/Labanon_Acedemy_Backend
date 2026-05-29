from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Message, DirectMessage
from .serializers import (
    MessageSerializer, MessageCreateSerializer, MessageReplySerializer,
    DirectMessageSerializer, DirectMessageCreateSerializer, DirectMessageThreadSerializer
)
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
        is_admin = user.is_staff or getattr(user, 'role', None) == 'admin'
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

        # Convert newlines to <br> for HTML email display, but keep the raw message for plaintext
        formatted_message = message.replace('\n', '<br>')
        
        # Determine a human readable title
        human_type = message_type.replace('_', ' ').title()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f9fafb;
                    margin: 0;
                    padding: 20px 0;
                }}
                .container {{
                    width: 100%;
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
                    border: 1px solid #f3f4f6;
                }}
                .header {{
                    background-color: #ca8a04; /* Brand Yellow/Orange */
                    color: #ffffff;
                    padding: 25px 20px;
                    text-align: center;
                }}
                .header h2 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                }}
                .header p {{
                    margin: 8px 0 0;
                    font-size: 14px;
                    opacity: 0.9;
                }}
                .content {{
                    padding: 30px;
                    color: #374151;
                    line-height: 1.6;
                }}
                .details-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 25px;
                    table-layout: fixed;
                }}
                .details-table th, .details-table td {{
                    padding: 12px 10px;
                    border-bottom: 1px solid #f3f4f6;
                    text-align: left;
                    font-size: 15px;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    word-break: break-word;
                }}
                .details-table th {{
                    width: 35%;
                    color: #6b7280;
                    font-weight: 600;
                }}
                .details-table td {{
                    color: #111827;
                    font-weight: 500;
                }}
                .message-box {{
                    background-color: #fefce8;
                    border-left: 4px solid #ca8a04;
                    padding: 20px;
                    margin-top: 10px;
                    border-radius: 0 8px 8px 0;
                    font-size: 15px;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    word-break: break-word;
                }}
                .footer {{
                    background-color: #f9fafb;
                    color: #9ca3af;
                    text-align: center;
                    padding: 20px;
                    font-size: 13px;
                    border-top: 1px solid #f3f4f6;
                }}
                .badge {{
                    background-color: #fef08a;
                    color: #854d0e;
                    padding: 4px 10px;
                    border-radius: 12px;
                    font-size: 12px;
                    font-weight: 700;
                    text-transform: uppercase;
                }}
                
                @media only screen and (max-width: 600px) {{
                    .container {{
                        width: 100% !important;
                        border-radius: 0 !important;
                    }}
                    .content {{
                        padding: 20px !important;
                    }}
                    .details-table th {{
                        width: 40% !important;
                        font-size: 14px !important;
                    }}
                    .details-table td {{
                        font-size: 14px !important;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>LightHub Academy</h2>
                    <p>New {human_type} Received</p>
                </div>
                <div class="content">
                    <table class="details-table">
                        <tr>
                            <th>Sender Name</th>
                            <td>{name}</td>
                        </tr>
                        <tr>
                            <th>Email Address</th>
                            <td><a href="mailto:{email}" style="color: #ca8a04; text-decoration: none;">{email}</a></td>
                        </tr>
                        <tr>
                            <th>Phone Number</th>
                            <td>{phone or 'Not Provided'}</td>
                        </tr>
                        <tr>
                            <th>Submission Type</th>
                            <td><span class="badge">{message_type.replace('_', ' ')}</span></td>
                        </tr>
                        <tr>
                            <th>Subject</th>
                            <td>{subject}</td>
                        </tr>
                    </table>
                    
                    <h3 style="margin: 0 0 10px 0; color: #111827; font-size: 18px;">Message Details</h3>
                    <div class="message-box">
                        {formatted_message}
                    </div>
                </div>
                <div class="footer">
                    &copy; LightHub Academy Admin Portal<br>
                    This is an automated system notification. Please do not reply directly to this email.
                </div>
            </div>
        </body>
        </html>
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


class DirectMessageViewSet(viewsets.ModelViewSet):
    """Viewset for direct messaging between admins and users."""
    serializer_class = DirectMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # Use default pagination

    def get_queryset(self):
        """Return all direct messages for current user (sent or received)."""
        user = self.request.user
        return DirectMessage.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).order_by('created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return DirectMessageCreateSerializer
        elif self.action == 'conversations':
            return DirectMessageThreadSerializer
        return DirectMessageSerializer

    def create(self, request, *args, **kwargs):
        """Send a direct message to a user."""
        serializer = DirectMessageCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        
        # Return full serialized message
        return_serializer = DirectMessageSerializer(instance, context={'request': request})
        return Response(return_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def conversations(self, request):
        """Get list of unique conversations for current user."""
        user = request.user
        
        # Get all unique thread_ids involving this user
        thread_ids = DirectMessage.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).values_list('thread_id', flat=True).distinct()
        
        # Get latest message from each thread
        conversations = []
        for thread_id in thread_ids:
            latest_msg = DirectMessage.objects.filter(thread_id=thread_id).order_by('-created_at').first()
            if latest_msg:
                conversations.append(latest_msg)
        
        serializer = DirectMessageThreadSerializer(
            conversations, 
            many=True, 
            context={'request': request}
        )
        
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def thread(self, request):
        """Get message thread with a specific user."""
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response(
                {'detail': 'user_id query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            other_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Construct thread_id
        ids = sorted([request.user.id, other_user.id])
        thread_id = f'direct_{ids[0]}_{ids[1]}'
        
        # Get all messages in thread
        messages = DirectMessage.objects.filter(thread_id=thread_id).order_by('created_at')
        
        # Mark unread messages as read
        messages.filter(recipient=request.user, is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        serializer = DirectMessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a direct message as read."""
        message = self.get_object()
        
        if message.recipient != request.user:
            return Response(
                {'detail': 'You can only mark your own messages as read'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        message.mark_as_read()
        return Response({'status': 'marked as read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread direct messages."""
        count = DirectMessage.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        return Response({'unread_count': count})


class UserSearchView(APIView):
    """Search for users by username, email, or name for direct messaging."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        role = request.query_params.get('role', '')
        limit = int(request.query_params.get('limit', 20))
        
        if len(query) < 2:
            return Response(
                {'detail': 'Query must be at least 2 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Build filter
        filter_q = Q(
            username__icontains=query
        ) | Q(
            email__icontains=query
        ) | Q(
            first_name__icontains=query
        ) | Q(
            last_name__icontains=query
        )
        
        # Filter by role if provided
        if role:
            filter_q &= Q(role=role)
        
        # Exclude current user
        users = User.objects.filter(filter_q).exclude(id=request.user.id).values(
            'id', 'username', 'email', 'first_name', 'last_name', 'role'
        )[:limit]
        
        # Add display name
        result = []
        for user in users:
            display_name = user['first_name'] or user['username']
            result.append({
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'first_name': user['first_name'],
                'last_name': user['last_name'],
                'role': user['role'],
                'display_name': display_name
            })
        
        return Response({'results': result})


class AdminEmailBroadcastView(APIView):
    """
    Endpoint for admins to broadcast an email to a specific role of users or all users.
    Triggers a Celery task.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        
        # Check permissions: User must be an admin OR a subadmin with can_manage_users
        is_admin = user.is_staff or getattr(user, 'role', None) == 'admin'
        is_authorized_sub = (
            hasattr(user, 'subadmin_profile') and 
            user.subadmin_profile.can_manage_users
        )
        
        if not (is_admin or is_authorized_sub):
            return Response(
                {'detail': 'You do not have permission to broadcast emails.'},
                status=status.HTTP_403_FORBIDDEN
            )
            
        audience = request.data.get('audience')
        subject = request.data.get('subject')
        message = request.data.get('message')
        
        if not all([audience, subject, message]):
            return Response(
                {'detail': 'audience, subject, and message are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        valid_audiences = ['all', 'student', 'tutor', 'institution']
        if audience not in valid_audiences:
            return Response(
                {'detail': f'Invalid audience. Must be one of {valid_audiences}.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Trigger Celery task
        from .tasks import send_broadcast_email_task
        send_broadcast_email_task.delay(audience, subject, message)
        
        return Response({'status': 'Broadcast task queued successfully.'}, status=status.HTTP_200_OK)