from rest_framework import serializers
from .models import Blog, BlogComment, BlogLike, BlogShare


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
    author_username = serializers.CharField(source='author.username', read_only=True)
    user_liked = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()

    class Meta:
        model = Blog
        fields = ['id', 'title', 'slug', 'content', 'image', 'excerpt', 'is_published', 'author', 'author_username', 
                  'created_at', 'updated_at', 'published_at', 'likes_count', 'comments_count', 'shares_count', 
                  'user_liked', 'comments']
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


class BlogShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogShare
        fields = ['id', 'blog', 'share_platform', 'created_at']
        read_only_fields = ['user', 'created_at']
