# Generated by Django 2.2.13 on 2021-05-26 17:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0006_auto_20210222_1758'),
    ]

    operations = [
        migrations.AddField(
            model_name='action',
            name='note',
            field=models.CharField(default='', max_length=200),
        ),
    ]
