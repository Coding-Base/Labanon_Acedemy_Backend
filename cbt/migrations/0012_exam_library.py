from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def place_existing_exams(apps, schema_editor):
    Country = apps.get_model('cbt', 'Country')
    ExamFolder = apps.get_model('cbt', 'ExamFolder')
    Exam = apps.get_model('cbt', 'Exam')

    country, _ = Country.objects.get_or_create(
        code='NG',
        defaults={
            'name': 'Nigeria',
            'slug': 'nigeria',
            'status': 'published',
            'is_visible': True,
        },
    )
    folder, _ = ExamFolder.objects.get_or_create(
        country=country,
        parent=None,
        slug='existing-cbt-exams',
        defaults={
            'name': 'Existing CBT Exams',
            'description': 'Existing CBT exams migrated from the original catalog.',
            'status': 'published',
            'is_visible': True,
        },
    )
    Exam.objects.filter(folder__isnull=True).update(folder=folder)


class Migration(migrations.Migration):
    dependencies = [
        ('cbt', '0011_exam_subject_select_limit'),
    ]

    operations = [
        migrations.CreateModel(
            name='Country',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('code', models.CharField(max_length=8, unique=True)),
                ('slug', models.SlugField(max_length=140, unique=True)),
                ('flag_image', models.ImageField(blank=True, null=True, upload_to='cbt_countries/')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('published', 'Published'), ('scheduled', 'Scheduled'), ('archived', 'Archived')], default='published', max_length=20)),
                ('is_visible', models.BooleanField(default=True)),
                ('available_from', models.DateTimeField(blank=True, null=True)),
                ('available_until', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['sort_order', 'name']},
        ),
        migrations.CreateModel(
            name='ExamFolder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=180)),
                ('slug', models.SlugField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('icon', models.CharField(blank=True, default='folder', max_length=80)),
                ('cover_image', models.ImageField(blank=True, null=True, upload_to='cbt_folders/')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('published', 'Published'), ('scheduled', 'Scheduled'), ('archived', 'Archived')], default='published', max_length=20)),
                ('is_visible', models.BooleanField(default=True)),
                ('available_from', models.DateTimeField(blank=True, null=True)),
                ('available_until', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('country', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='folders', to='cbt.country')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='cbt.examfolder')),
            ],
            options={'ordering': ['sort_order', 'name']},
        ),
        migrations.AddConstraint(
            model_name='examfolder',
            constraint=models.UniqueConstraint(fields=('country', 'parent', 'slug'), name='unique_folder_slug_per_country_parent'),
        ),
        migrations.AddField(
            model_name='exam',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exams', to='cbt.examfolder'),
        ),
        migrations.AddField(model_name='exam', name='institution', field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='exam', name='provider', field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='exam', name='exam_type', field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name='exam', name='year', field=models.CharField(blank=True, max_length=10)),
        migrations.AddField(model_name='exam', name='difficulty', field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name='exam', name='sort_order', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='exam', name='status', field=models.CharField(choices=[('draft', 'Draft'), ('published', 'Published'), ('scheduled', 'Scheduled'), ('archived', 'Archived')], default='published', max_length=20)),
        migrations.AddField(model_name='exam', name='is_visible', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='exam', name='available_from', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='exam', name='available_until', field=models.DateTimeField(blank=True, null=True)),
        migrations.AlterField(model_name='exam', name='title', field=models.CharField(max_length=255)),
        migrations.AlterModelOptions(
            name='exam',
            options={'ordering': ['sort_order', 'title']},
        ),
        migrations.RunPython(place_existing_exams, migrations.RunPython.noop),
    ]
