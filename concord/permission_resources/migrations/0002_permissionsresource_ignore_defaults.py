# Generated by Django 2.1.2 on 2018-10-20 20:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('permission_resources', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionsresource',
            name='ignore_defaults',
            field=models.BooleanField(default=False),
        ),
    ]
