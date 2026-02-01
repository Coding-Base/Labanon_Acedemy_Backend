from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

from blog.models import Blog

class Command(BaseCommand):
    help = 'Create a sample published blog post for sitemap verification'

    def add_arguments(self, parser):
        parser.add_argument('--title', default='Sample Blog Post', help='Title for the sample blog')
        parser.add_argument('--author-id', type=int, help='ID of existing author to use')
        parser.add_argument('--slug', help='Slug to use (defaults from title)')
        parser.add_argument('--content', help='HTML content for the post', default='<p>This is a sample blog post used to verify sitemap generation.</p>')

    def handle(self, *args, **options):
        User = get_user_model()
        author = None

        if options.get('author_id'):
            try:
                author = User.objects.get(pk=options['author_id'])
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"No user with id={options['author_id']} found. Falling back to first user or creating one."))

        if not author:
            author = User.objects.filter(is_active=True).first()

        if not author:
            # Create a lightweight sample user if none exist
            username = 'sampleuser'
            email = 'sampleuser@example.com'
            password = 'sample-password-please-change'
            author = User.objects.create_user(username=username, email=email, password=password)
            author.is_staff = True
            author.save()
            self.stdout.write(self.style.SUCCESS(f"Created sample user '{username}' (id={author.pk})"))

        title = options.get('title')
        slug = options.get('slug') or slugify(title)
        content = options.get('content')

        # Avoid creating duplicate sample posts with same slug
        blog, created = Blog.objects.get_or_create(
            slug=slug,
            defaults={
                'author': author,
                'title': title,
                'content': content,
                'is_published': True,
                'published_at': timezone.now(),
            }
        )

        if not created:
            blog.is_published = True
            blog.published_at = timezone.now()
            blog.content = content
            blog.title = title
            blog.save()
            self.stdout.write(self.style.SUCCESS(f"Updated existing blog (slug={slug}) and marked published."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Created sample blog '{title}' (slug={slug})."))

        # Print the URL to check sitemap and public page
        url = f"/blog/{blog.slug}/"
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Check the public page at: ") + self.style.SUCCESS(url))
        self.stdout.write(self.style.HTTP_INFO("Afterwards refresh /sitemap.xml to see the entry."))
