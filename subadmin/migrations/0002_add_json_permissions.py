from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subadmin', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subadmin',
            name='permissions',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
