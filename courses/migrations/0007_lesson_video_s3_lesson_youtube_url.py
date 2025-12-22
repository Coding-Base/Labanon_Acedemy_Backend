# Generated migration for courses app to add video_s3 and youtube_url fields

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0006_course_end_date_course_meeting_link_and_more'),
        ('videos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='video_s3',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lessons', to='videos.video'),
        ),
        migrations.AddField(
            model_name='lesson',
            name='youtube_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
