from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def copy_existing_library_links(apps, schema_editor):
    ExamFolder = apps.get_model('cbt', 'ExamFolder')
    FolderExam = apps.get_model('cbt', 'FolderExam')

    for folder in ExamFolder.objects.exclude(country_id__isnull=True).iterator():
        folder.country_tags.add(folder.country_id)

    for folder in ExamFolder.objects.iterator():
        for exam in folder.exams.all().iterator():
            FolderExam.objects.get_or_create(folder_id=folder.id, exam_id=exam.id)


class Migration(migrations.Migration):
    dependencies = [('cbt', '0013_question_assignment')]

    operations = [
        migrations.RemoveConstraint(
            model_name='examfolder',
            name='unique_folder_slug_per_country_parent',
        ),
        migrations.AlterField(
            model_name='examfolder',
            name='country',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='legacy_folders',
                to='cbt.country',
            ),
        ),
        migrations.AddField(
            model_name='examfolder',
            name='country_tags',
            field=models.ManyToManyField(blank=True, related_name='tagged_folders', to='cbt.country'),
        ),
        migrations.AddField(
            model_name='examfolder',
            name='status_before_archive',
            field=models.CharField(blank=True, choices=[('draft', 'Draft'), ('published', 'Published'), ('scheduled', 'Scheduled'), ('archived', 'Archived')], max_length=20),
        ),
        migrations.AddConstraint(
            model_name='examfolder',
            constraint=models.UniqueConstraint(fields=('parent', 'slug'), name='unique_folder_slug_per_parent'),
        ),
        migrations.CreateModel(
            name='FolderExam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='folder_links', to='cbt.exam')),
                ('folder', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_links', to='cbt.examfolder')),
            ],
            options={'ordering': ['sort_order', 'created_at']},
        ),
        migrations.CreateModel(
            name='FolderSubject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('folder', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subject_links', to='cbt.examfolder')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='folder_links', to='cbt.subject')),
            ],
            options={'ordering': ['sort_order', 'created_at']},
        ),
        migrations.AddConstraint(
            model_name='folderexam',
            constraint=models.UniqueConstraint(fields=('folder', 'exam'), name='unique_folder_exam_link'),
        ),
        migrations.AddConstraint(
            model_name='foldersubject',
            constraint=models.UniqueConstraint(fields=('folder', 'subject'), name='unique_folder_subject_link'),
        ),
        migrations.RunPython(copy_existing_library_links, migrations.RunPython.noop),
    ]
