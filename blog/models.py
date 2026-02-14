from django.db import models
from django.conf import settings
from django.utils.text import slugify


class Blog(models.Model):
    """Blog post model for platform news and announcements"""
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_posts')
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    content = models.TextField()
    image = models.CharField(max_length=512, blank=True)  # URL or file path
    image_description = models.CharField(max_length=255, blank=True, help_text="Alt text and description for the featured image")
    excerpt = models.TextField(max_length=500, blank=True)
    # SEO / Metadata for search engines
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)
    meta_keywords = models.CharField(max_length=512, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Engagement stats
    likes_count = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    shares_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class BlogComment(models.Model):
    """Comments on blog posts with support for nested replies"""
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='comments')
    # Allow anonymous comments: author may be null and a display name can be provided
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_comments', null=True, blank=True)
    author_name = models.CharField(max_length=100, blank=True)
    content = models.TextField()
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    likes_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        author_display = self.author.username if self.author else (self.author_name or 'Anonymous')
        return f"Comment by {author_display} on {self.blog.title}"


class BlogLike(models.Model):
    """Likes for blog posts and comments"""
    LIKE_CHOICES = [
        ('blog', 'Blog Post'),
        ('comment', 'Comment'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blog_likes')
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, null=True, blank=True, related_name='likes')
    comment = models.ForeignKey(BlogComment, on_delete=models.CASCADE, null=True, blank=True, related_name='likes')
    like_type = models.CharField(max_length=10, choices=LIKE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('user', 'blog', 'comment'),)  # Prevent duplicate likes
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} liked a {self.like_type}"


class BlogShare(models.Model):
    """Track blog shares"""
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    share_platform = models.CharField(max_length=50, blank=True)  # e.g., 'twitter', 'facebook', 'email'
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.blog.title} shared on {self.share_platform or 'platform'}"
