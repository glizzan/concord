# Generated by Django 2.2.4 on 2020-09-14 19:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0002_remove_action_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='templatemodel',
            name='supplied_fields',
            field=models.CharField(max_length=5000),
        ),
    ]
