from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import DirectMessage
from .serializers import (
    DirectMessageSerializer, DirectMessageCreateSerializer, DirectMessageThreadSerializer
)
from rest_framework.views import APIView

User = get_user_model()


class DirectMessageViewSet(viewsets.ModelViewSet):
    """Viewset for direct messaging between admins and users."""
    serializer_class = DirectMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return all direct messages for current user (sent or received)."""
        user = self.request.user
        return DirectMessage.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).order_by('created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return DirectMessageCreateSerializer
        elif self.action == 'list' or self.action == 'conversations':
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
        """
        Get list of unique conversations for current user.
        Returns last message info for each conversation thread.
        """
        user = request.user
        
        # Get all unique thread_ids involving this user
        messages = DirectMessage.objects.filter(
            Q(sender=user) | Q(recipient=user)
        ).values_list('thread_id', flat=True).distinct()
        
        # Get latest message from each thread
        conversations = []
        for thread_id in messages:
            latest_msg = DirectMessage.objects.filter(thread_id=thread_id).order_by('-created_at').first()
            if latest_msg:
                conversations.append(latest_msg)
        
        # Serialize using DirectMessageThreadSerializer
        serializer = DirectMessageThreadSerializer(
            conversations, 
            many=True, 
            context={'request': request}
        )
        
        # Paginate
        page = self.paginate_queryset(serializer.data)
        if page is not None:
            return self.get_paginated_response(page)
        
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def thread(self, request):
        """
        Get message thread with a specific user.
        Query params: ?user_id=<id> or ?thread_id=<id>
        """
        user_id = request.query_params.get('user_id')
        thread_id = request.query_params.get('thread_id')
        
        if not user_id and not thread_id:
            return Response(
                {'detail': 'Provide either user_id or thread_id as query parameter'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If user_id provided, construct thread_id
        if user_id:
            try:
                other_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            
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
        role = request.query_params.get('role', '')  # Optional: filter by role
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
