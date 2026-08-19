# Generated manually to populate default categories and associate existing subjects
from django.db import migrations
import uuid

def populate_default_categories(apps, schema_editor):
    Category = apps.get_model('lessons', 'Category')
    Subject = apps.get_model('lessons', 'Subject')

    # Create default categories
    secondary = Category.objects.create(
        name='Secondary',
        description='Secondary school subjects',
        color='#22C55E',  # Green
        order=1
    )
    university = Category.objects.create(
        name='University',
        description='University level subjects',
        color='#3B82F6',  # Blue
        order=2
    )

    # Distribute existing subjects based on keyword matching
    for subject in Subject.objects.all():
        lower_name = subject.name.toLowerCase() if hasattr(subject.name, 'toLowerCase') else subject.name.lower()
        if 'university' in lower_name or 'engineering' in lower_name or 'computer' in lower_name:
            subject.category = university
        else:
            subject.category = secondary
        subject.save()

def rollback_categories(apps, schema_editor):
    Category = apps.get_model('lessons', 'Category')
    Category.objects.filter(name__in=['Secondary', 'University']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('lessons', '0005_category_subject_category'),
    ]

    operations = [
        migrations.RunPython(populate_default_categories, reverse_code=rollback_categories),
    ]
