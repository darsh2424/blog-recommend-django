# Generated by Django 5.2.1 on 2025-07-04 12:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_alter_userpostactivity_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userpostactivity',
            name='reason',
            field=models.CharField(choices=[('typo', 'Fixed typos'), ('info', 'Added more information'), ('image', 'Updated image'), ('structure', 'Improved structure'), ('other', 'Other (please specify)')], max_length=20, null=True),
        ),
    ]
