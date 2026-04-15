# backend/materials/migrations/0001_initial.py

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('courses', '0001_initial'),  # Depends on courses app for Payment FK
    ]

    operations = [
        migrations.CreateModel(
            name='Material',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='Name/title of the material', max_length=255)),
                ('description', models.TextField(blank=True, help_text='Brief description of the material')),
                ('area', models.CharField(choices=[('academy', 'Academy'), ('research', 'Research'), ('interview', 'Interview Prep'), ('science', 'Science'), ('art', 'Art'), ('discovery', 'Discovery'), ('invention', 'Invention'), ('project', 'Project'), ('other', 'Other')], help_text='Category area (e.g., Academy, Research, Science)', max_length=50)),
                ('creator_name', models.CharField(help_text='Name to display as creator (typically author name)', max_length=255)),
                ('licenses', models.CharField(help_text='License type (e.g., CC-BY-4.0, MIT, All Rights Reserved)', max_length=255)),
                ('topic_category', models.CharField(db_index=True, help_text='Topic for search/filter (e.g., Maths, Physics, Biology)', max_length=100)),
                ('file_source', models.CharField(choices=[('upload', 'Direct Upload'), ('gdrive', 'Google Drive Link')], help_text='Type of file storage', max_length=20)),
                ('file_url', models.URLField(blank=True, help_text='S3/CloudFront signed URL for direct uploads', null=True)),
                ('gdrive_link', models.URLField(blank=True, help_text='Google Drive sharing link', null=True)),
                ('file_size', models.BigIntegerField(help_text='File size in bytes')),
                ('file_name', models.CharField(blank=True, help_text='Original filename for reference', max_length=255)),
                ('price', models.DecimalField(decimal_places=2, default=0, help_text='Price in local currency. 0 = FREE', max_digits=10)),
                ('currency', models.CharField(default='NGN', help_text='ISO 4217 currency code', max_length=3)),
                ('total_revenue', models.DecimalField(decimal_places=2, default=0, help_text='Total revenue from all purchases', max_digits=15)),
                ('is_published', models.BooleanField(db_index=True, default=True, help_text='Is material visible in marketplace')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(help_text='Admin who created this material', on_delete=django.db.models.deletion.PROTECT, related_name='materials_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='MaterialPurchase',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('accessed_at', models.DateTimeField(auto_now_add=True, help_text='When user first got access')),
                ('download_count', models.IntegerField(default=0, help_text='How many times user downloaded this material')),
                ('last_downloaded_at', models.DateTimeField(blank=True, help_text='When user last downloaded', null=True)),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='purchases', to='materials.material')),
                ('payment', models.OneToOneField(blank=True, help_text='Payment record if material was purchased (NULL if free)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='material_purchase', to='courses.payment')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='material_purchases', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-accessed_at'],
                'unique_together': {('user', 'material')},
            },
        ),
        migrations.CreateModel(
            name='MaterialDownload',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('download_token', models.CharField(help_text='Unique token for tracking', max_length=255, unique=True)),
                ('link_expires_at', models.DateTimeField(help_text='When the download link expires')),
                ('downloaded_at', models.DateTimeField(blank=True, help_text='When user actually clicked/downloaded', null=True)),
                ('ip_address', models.CharField(blank=True, help_text="User's IP address", max_length=45)),
                ('user_agent', models.TextField(blank=True, help_text='Browser user agent')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='download_records', to='materials.material')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='material_downloads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='material',
            index=models.Index(fields=['is_published', '-created_at'], name='materials_m_is_publ_idx'),
        ),
        migrations.AddIndex(
            model_name='material',
            index=models.Index(fields=['topic_category'], name='materials_m_topic_c_idx'),
        ),
        migrations.AddIndex(
            model_name='material',
            index=models.Index(fields=['area'], name='materials_m_area_idx'),
        ),
        migrations.AddIndex(
            model_name='materialpurchase',
            index=models.Index(fields=['user', '-accessed_at'], name='materials_m_user_id_accessed_idx'),
        ),
        migrations.AddIndex(
            model_name='materialpurchase',
            index=models.Index(fields=['material', '-accessed_at'], name='materials_m_material_accessed_idx'),
        ),
        migrations.AddIndex(
            model_name='materialdownload',
            index=models.Index(fields=['user', '-created_at'], name='materials_m_user_id_created_idx'),
        ),
        migrations.AddIndex(
            model_name='materialdownload',
            index=models.Index(fields=['download_token'], name='materials_m_download_token_idx'),
        ),
    ]
