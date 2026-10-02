from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('cbt', '0012_exam_library')]

    operations = [
        migrations.CreateModel(
            name='QuestionAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='cbt.question')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='question_assignments', to='cbt.subject')),
            ],
            options={'ordering': ['sort_order', '-created_at']},
        ),
        migrations.AddConstraint(
            model_name='questionassignment',
            constraint=models.UniqueConstraint(fields=('question', 'subject'), name='unique_question_subject_assignment'),
        ),
    ]
