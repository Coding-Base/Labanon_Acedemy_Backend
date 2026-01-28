from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('videos', '0002_alter_video_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='video',
            name='cloudfront_url',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='video',
            name='cloudfront_thumbnail_url',
            field=models.TextField(null=True, blank=True),
        ),
    ]
