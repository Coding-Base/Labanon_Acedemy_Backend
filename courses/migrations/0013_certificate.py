# Generated migration for Certificate model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0012_change_institution_is_active_default'),
    ]

    operations = [
        migrations.CreateModel(
            name='Certificate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('certificate_id', models.CharField(help_text='Unique certificate ID', max_length=50, unique=True)),
                ('issue_date', models.DateTimeField(auto_now_add=True)),
                ('completion_date', models.DateField(blank=True, null=True)),
                ('is_downloaded', models.BooleanField(default=False)),
                ('download_count', models.PositiveIntegerField(default=0)),
                ('last_downloaded_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='certificates', to='courses.course')),
                ('enrollment', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='certificate', to='courses.enrollment')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='certificates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('user', 'course')},
            },
        ),
        migrations.AddIndex(
            model_name='certificate',
            index=models.Index(fields=['user', '-created_at'], name='courses_cert_user_id_idx'),
        ),
        migrations.AddIndex(
            model_name='certificate',
            index=models.Index(fields=['certificate_id'], name='courses_cert_cert_id_idx'),
        ),
    ]
