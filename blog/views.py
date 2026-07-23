from rest_framework import viewsets, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.utils import timezone
from django.db.models import Count, Q
from .models import Blog, BlogComment, BlogLike, BlogShare, BlogCategory
from .serializers import BlogSerializer, BlogCommentSerializer, BlogLikeSerializer, BlogShareSerializer, BlogCategorySerializer
from users.permissions import IsMasterAdmin
from django.shortcuts import render, get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
import os
import uuid
import logging
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings


class BlogCategoryViewSet(viewsets.ModelViewSet):
    """Blog Category API endpoints"""
    queryset = BlogCategory.objects.all().order_by('name')
    serializer_class = BlogCategorySerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    @action(detail=False, methods=['get'])
    def top(self, request):
        """Get top 5 categories ordered by number of published blog posts"""
        top_cats = BlogCategory.objects.annotate(
            pub_count=Count('blogs', filter=Q(blogs__is_published=True))
        ).order_by('-pub_count', 'name')[:5]
        serializer = self.get_serializer(top_cats, many=True)
        return Response(serializer.data)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class BlogViewSet(viewsets.ModelViewSet):
    """Blog API endpoints - admins can create/edit, everyone can read published"""
    queryset = Blog.objects.all()
    serializer_class = BlogSerializer
    pagination_class = StandardResultsSetPagination
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        # Admins see all, others see only published
        if self.request.user and (self.request.user.is_staff or (hasattr(self.request.user, 'role') and self.request.user.role == 'admin')):
            return Blog.objects.all().order_by('-created_at')
        return Blog.objects.filter(is_published=True).order_by('-published_at', '-created_at')

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsMasterAdmin]
        else:
            permission_classes = [permissions.IsAuthenticatedOrReadOnly]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=False, methods=['get'])
    def published(self, request):
        """Get all published blogs with pagination and optional category filtering"""
        queryset = Blog.objects.filter(is_published=True)
        cat = request.query_params.get('category')
        search = request.query_params.get('search')
        if cat:
            if cat.isdigit():
                queryset = queryset.filter(category_id=int(cat))
            else:
                queryset = queryset.filter(category__slug=cat)
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(excerpt__icontains=search) | Q(content__icontains=search))

        queryset = queryset.order_by('-published_at', '-created_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


    @action(detail=True, methods=['post'], permission_classes=[IsMasterAdmin])
    def publish(self, request, pk=None):
        """Publish a blog post"""
        blog = self.get_object()
        blog.is_published = True
        blog.published_at = timezone.now()
        blog.save()
        serializer = self.get_serializer(blog)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsMasterAdmin])
    def unpublish(self, request, pk=None):
        """Unpublish a blog post"""
        blog = self.get_object()
        blog.is_published = False
        blog.save()
        serializer = self.get_serializer(blog)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, pk=None):
        """Toggle like on a blog post"""
        blog = self.get_object()
        like, created = BlogLike.objects.get_or_create(
            user=request.user,
            blog=blog,
            like_type='blog'
        )
        
        if not created:
            like.delete()
            blog.likes_count = max(0, blog.likes_count - 1)
            blog.save()
            return Response({'liked': False, 'likes_count': blog.likes_count})
        
        blog.likes_count += 1
        blog.save()
        serializer = BlogLikeSerializer(like)
        return Response({'liked': True, 'likes_count': blog.likes_count, 'like': serializer.data})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def share(self, request, pk=None):
        """Record a blog share"""
        blog = self.get_object()
        platform = request.data.get('platform', '')
        
        share = BlogShare.objects.create(
            blog=blog,
            user=request.user,
            share_platform=platform
        )
        
        blog.shares_count += 1
        blog.save()
        
        serializer = BlogShareSerializer(share)
        return Response({'shares_count': blog.shares_count, 'share': serializer.data})


class BlogCommentViewSet(viewsets.ModelViewSet):
    """Manage comments on blog posts. Allow anonymous posting with an author_name."""
    queryset = BlogComment.objects.all()
    serializer_class = BlogCommentSerializer
    # Allow anyone to submit comments (we will attach request.user when available)
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        blog_id = self.request.query_params.get('blog_id')
        if blog_id:
            return BlogComment.objects.filter(blog_id=blog_id, parent_comment__isnull=True).order_by('-created_at')
        return BlogComment.objects.filter(parent_comment__isnull=True).order_by('-created_at')

    def perform_create(self, serializer):
        # If authenticated, set the author FK; otherwise accept an author_name field
        if self.request.user and self.request.user.is_authenticated:
            serializer.save(author=self.request.user)
        else:
            # Pop author_name if provided and save as field on the comment
            author_name = self.request.data.get('author_name') or serializer.validated_data.get('author_name') if hasattr(serializer, 'validated_data') else self.request.data.get('author_name')
            serializer.save(author=None, author_name=(author_name or '').strip())

        blog = serializer.instance.blog
        blog.comments_count += 1
        blog.save()

    def perform_destroy(self, instance):
        blog = instance.blog
        instance.delete()
        blog.comments_count = max(0, blog.comments_count - 1)
        blog.save()

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, pk=None):
        """Toggle like on a comment"""
        comment = self.get_object()
        like, created = BlogLike.objects.get_or_create(
            user=request.user,
            comment=comment,
            like_type='comment'
        )
        
        if not created:
            like.delete()
            comment.likes_count = max(0, comment.likes_count - 1)
            comment.save()
            return Response({'liked': False, 'likes_count': comment.likes_count})
        
        comment.likes_count += 1
        comment.save()
        serializer = BlogLikeSerializer(like)
        return Response({'liked': True, 'likes_count': comment.likes_count, 'like': serializer.data})


def blog_detail_view(request, slug):
    """Server-rendered blog detail page with meta tags for SEO/crawlers."""
    blog = get_object_or_404(Blog, slug=slug, is_published=True)
    context = {
        'title': blog.title,
        'content': blog.content,
        'excerpt': blog.excerpt,
        'meta_title': blog.meta_title,
        'meta_description': blog.meta_description,
        'meta_keywords': blog.meta_keywords,
        'published_at': blog.published_at,
        'author': blog.author,
    }
    return render(request, 'blog_detail.html', context)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_blog_image(request):
    """Endpoint for uploading images inside Quill blog editor."""
    file_obj = request.FILES.get('image') or request.FILES.get('file')
    if not file_obj:
        return Response({'detail': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)
    
    ext = os.path.splitext(file_obj.name)[1].lower()
    filename = f"blog_images/{uuid.uuid4()}{ext}"
    saved_path = default_storage.save(filename, ContentFile(file_obj.read()))
    url = default_storage.url(saved_path)
    return Response({'url': url})

