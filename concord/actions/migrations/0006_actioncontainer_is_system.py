# Generated by Django 2.2.4 on 2020-06-01 20:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0005_actioncontainer_trigger_action'),
    ]

    operations = [
        migrations.AddField(
            model_name='actioncontainer',
            name='is_system',
            field=models.BooleanField(default=False),
        ),
    ]