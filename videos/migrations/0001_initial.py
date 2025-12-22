# Generated migration for videos app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Video',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('original_file_name', models.CharField(max_length=255)),
                ('file_size', models.BigIntegerField()),
                ('duration', models.FloatField(blank=True, null=True)),
                ('s3_original_key', models.CharField(max_length=512)),
                ('s3_hls_manifest_key', models.CharField(blank=True, max_length=512)),
                ('s3_hls_folder_key', models.CharField(blank=True, max_length=512)),
                ('cloudfront_url', models.URLField(blank=True, null=True)),
                ('cloudfront_thumbnail_url', models.URLField(blank=True, null=True)),
                ('status', models.CharField(choices=[('uploading', 'Uploading'), ('processing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')], default='uploading', max_length=20)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('youtube_url', models.URLField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='videos', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='VideoUploadSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('upload_id', models.CharField(max_length=255)),
                ('parts_uploaded', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('video', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='upload_session', to='videos.video')),
            ],
        ),
        migrations.CreateModel(
            name='VideoConversionTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('celery_task_id', models.CharField(blank=True, max_length=255, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('progress', models.IntegerField(default=0)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('video', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='conversion_task', to='videos.video')),
            ],
        ),
    ]
