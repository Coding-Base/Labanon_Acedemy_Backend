# Generated for lesson folder/subfolder/topic organization

import uuid
from django.db import migrations, models
import django.db.models.deletion


def create_general_subfolders(apps, schema_editor):
    Subject = apps.get_model('lessons', 'Subject')
    LessonSubfolder = apps.get_model('lessons', 'LessonSubfolder')
    Topic = apps.get_model('lessons', 'Topic')

    for subject in Subject.objects.all():
        subfolder, _ = LessonSubfolder.objects.get_or_create(
            subject=subject,
            name='General',
            defaults={
                'description': '',
                'is_custom': False,
                'order': 0,
            },
        )
        Topic.objects.filter(subject=subject, subfolder__isnull=True).update(subfolder=subfolder)


def remove_general_subfolders(apps, schema_editor):
    LessonSubfolder = apps.get_model('lessons', 'LessonSubfolder')
    Topic = apps.get_model('lessons', 'Topic')
    general_subfolders = LessonSubfolder.objects.filter(name='General', is_custom=False)
    Topic.objects.filter(subfolder__in=general_subfolders).update(subfolder=None)
    general_subfolders.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('lessons', '0002_lessoncontent_meta_description_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LessonSubfolder',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('is_custom', models.BooleanField(default=False, help_text='Whether this was created by admin via custom input')),
                ('order', models.PositiveIntegerField(default=0, help_text='Display order within subject')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subfolders', to='lessons.subject')),
            ],
            options={
                'ordering': ['subject', 'order', 'name'],
                'unique_together': {('subject', 'name')},
            },
        ),
        migrations.AddField(
            model_name='topic',
            name='subfolder',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='topics', to='lessons.lessonsubfolder'),
        ),
        migrations.AddField(
            model_name='lessoncontent',
            name='tags',
            field=models.CharField(blank=True, help_text='Comma-separated lesson search tags', max_length=500),
        ),
        migrations.RunPython(create_general_subfolders, remove_general_subfolders),
        migrations.AlterField(
            model_name='topic',
            name='subfolder',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='topics', to='lessons.lessonsubfolder'),
        ),
        migrations.AlterUniqueTogether(
            name='topic',
            unique_together={('subfolder', 'name')},
        ),
    ]
