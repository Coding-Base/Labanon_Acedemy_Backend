from rest_framework import serializers
from .models import Blog, BlogComment, BlogLike, BlogShare
import logging
import os
import uuid
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings

try:
    import bleach
except Exception:
    bleach = None
    logging.getLogger(__name__).warning('bleach not installed; HTML sanitization will be skipped')


class BlogLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogLike
        fields = ['id', 'user', 'like_type', 'created_at']
        read_only_fields = ['user', 'created_at']


class BlogCommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source='author.username', read_only=True)
    author_id = serializers.IntegerField(source='author.id', read_only=True)
    user_liked = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()

    class Meta:
        model = BlogComment
        fields = ['id', 'blog', 'author', 'author_username', 'author_id', 'content', 'parent_comment', 
                  'likes_count', 'user_liked', 'replies', 'created_at', 'updated_at']
        read_only_fields = ['author', 'created_at', 'updated_at', 'likes_count']

    def get_user_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return BlogLike.objects.filter(
                comment=obj, 
                user=request.user,
                like_type='comment'
            ).exists()
        return False

    def get_replies(self, obj):
        replies = obj.replies.all()
        return BlogCommentSerializer(replies, many=True, context=self.context).data


class BlogSerializer(serializers.ModelSerializer):
    # Accept uploaded image via a write-only ImageField to allow multipart/form-data
    image_file = serializers.ImageField(write_only=True, required=False)
    author_username = serializers.CharField(source='author.username', read_only=True)
    user_liked = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()

    class Meta:
        model = Blog
        # include 'image_file' (write-only) so multipart uploads validate
        fields = ['id', 'title', 'slug', 'content', 'image', 'image_file', 'excerpt', 'is_published', 'author', 'author_username', 
                  'created_at', 'updated_at', 'published_at', 'likes_count', 'comments_count', 'shares_count', 
                  'user_liked', 'comments', 'meta_title', 'meta_description', 'meta_keywords']
        read_only_fields = ['slug', 'author', 'created_at', 'updated_at', 'likes_count', 'comments_count', 'shares_count']

    def get_user_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return BlogLike.objects.filter(
                blog=obj, 
                user=request.user,
                like_type='blog'
            ).exists()
        return False

    def get_comments(self, obj):
        comments = obj.comments.filter(parent_comment__isnull=True)  # Only top-level comments
        return BlogCommentSerializer(comments, many=True, context=self.context).data

    def _sanitize_html(self, html: str) -> str:
        """Sanitize HTML content using bleach if available."""
        if not html:
            return ''
        if not bleach:
            return html

        allowed_tags = [
            'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'a', 'ul', 'ol', 'li',
            'h1', 'h2', 'h3', 'blockquote', 'code', 'pre', 'img', 'span'
        ]
        allowed_attrs = {
            '*': ['style'],
            'a': ['href', 'title', 'target', 'rel'],
            'img': ['src', 'alt', 'title', 'width', 'height']
        }
        cleaned = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
        return cleaned

    def create(self, validated_data):
        # Prefer an uploaded file provided under 'image_file' (write-only) when present
        image_file = validated_data.pop('image_file', None)
        if image_file and isinstance(image_file, UploadedFile):
            ext = os.path.splitext(image_file.name)[1] or ''
            filename = f"blog_images/{uuid.uuid4().hex}{ext}"
            
            # Use Cloudinary explicitly for blog images
            use_cloudinary = os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes')
            
            if use_cloudinary:
                try:
                    from cloudinary_storage.storage import MediaCloudinaryStorage
                    storage = MediaCloudinaryStorage()
                except ImportError:
                    storage = default_storage
            else:
                storage = default_storage
            
            saved_name = storage.save(filename, ContentFile(image_file.read()))
            try:
                image_url = storage.url(saved_name)
            except Exception:
                image_url = f"{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
            
            # Prepend site URL if needed
            if image_url.startswith('/') and getattr(settings, 'SITE_URL', None):
                image_url = f"{settings.SITE_URL.rstrip('/')}{image_url}"
            
            validated_data['image'] = image_url
        else:
            # Fallback: if 'image' key contains an UploadedFile (older clients), handle it
            image = validated_data.get('image')
            if image and isinstance(image, UploadedFile):
                ext = os.path.splitext(image.name)[1] or ''
                filename = f"blog_images/{uuid.uuid4().hex}{ext}"
                
                # Use Cloudinary explicitly for blog images
                use_cloudinary = os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes')
                
                if use_cloudinary:
                    try:
                        from cloudinary_storage.storage import MediaCloudinaryStorage
                        storage = MediaCloudinaryStorage()
                    except ImportError:
                        storage = default_storage
                else:
                    storage = default_storage
                
                saved_name = storage.save(filename, ContentFile(image.read()))
                try:
                    image_url = storage.url(saved_name)
                except Exception:
                    image_url = f"{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
                
                # Prepend site URL if needed
                if image_url.startswith('/') and getattr(settings, 'SITE_URL', None):
                    image_url = f"{settings.SITE_URL.rstrip('/')}{image_url}"
                
                validated_data['image'] = image_url

        # Sanitize content and excerpt and meta fields
        content = validated_data.get('content', '')
        excerpt = validated_data.get('excerpt', '')
        validated_data['content'] = self._sanitize_html(content)
        validated_data['excerpt'] = bleach.clean(excerpt, strip=True) if bleach and excerpt else excerpt
        # sanitize meta_description (strip tags)
        if 'meta_description' in validated_data and validated_data['meta_description']:
            validated_data['meta_description'] = bleach.clean(validated_data['meta_description'], strip=True) if bleach else validated_data['meta_description']
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Handle uploaded image files on update as well (support 'image_file' write-only field)
        image_file = validated_data.pop('image_file', None)
        if image_file and isinstance(image_file, UploadedFile):
            ext = os.path.splitext(image_file.name)[1] or ''
            filename = f"blog_images/{uuid.uuid4().hex}{ext}"
            
            # Use Cloudinary explicitly for blog images
            use_cloudinary = os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes')
            
            if use_cloudinary:
                try:
                    from cloudinary_storage.storage import MediaCloudinaryStorage
                    storage = MediaCloudinaryStorage()
                except ImportError:
                    storage = default_storage
            else:
                storage = default_storage
            
            saved_name = storage.save(filename, ContentFile(image_file.read()))
            try:
                image_url = storage.url(saved_name)
            except Exception:
                image_url = f"{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
            
            # Prepend site URL if needed
            if image_url.startswith('/') and getattr(settings, 'SITE_URL', None):
                image_url = f"{settings.SITE_URL.rstrip('/')}{image_url}"
            
            validated_data['image'] = image_url
        else:
            image = validated_data.get('image')
            if image and isinstance(image, UploadedFile):
                ext = os.path.splitext(image.name)[1] or ''
                filename = f"blog_images/{uuid.uuid4().hex}{ext}"
                
                # Use Cloudinary explicitly for blog images
                use_cloudinary = os.environ.get('USE_CLOUDINARY', 'False').lower() in ('1', 'true', 'yes')
                
                if use_cloudinary:
                    try:
                        from cloudinary_storage.storage import MediaCloudinaryStorage
                        storage = MediaCloudinaryStorage()
                    except ImportError:
                        storage = default_storage
                else:
                    storage = default_storage
                
                saved_name = storage.save(filename, ContentFile(image.read()))
                try:
                    image_url = storage.url(saved_name)
                except Exception:
                    image_url = f"{getattr(settings, 'MEDIA_URL', '/media/')}{saved_name}"
                
                # Prepend site URL if needed
                if image_url.startswith('/') and getattr(settings, 'SITE_URL', None):
                    image_url = f"{settings.SITE_URL.rstrip('/')}{image_url}"
                
                validated_data['image'] = image_url

        if 'content' in validated_data:
            validated_data['content'] = self._sanitize_html(validated_data.get('content', ''))
        if 'excerpt' in validated_data and bleach:
            validated_data['excerpt'] = bleach.clean(validated_data.get('excerpt', ''), strip=True)
        if 'meta_description' in validated_data and validated_data['meta_description'] and bleach:
            validated_data['meta_description'] = bleach.clean(validated_data['meta_description'], strip=True)
        return super().update(instance, validated_data)


class BlogShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogShare
        fields = ['id', 'blog', 'share_platform', 'created_at']
        read_only_fields = ['user', 'created_at']
