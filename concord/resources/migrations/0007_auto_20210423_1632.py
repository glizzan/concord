# Generated by Django 2.2.13 on 2021-04-23 16:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0006_document'),
    ]

    operations = [
        migrations.AlterField(
            model_name='simplelist',
            name='description',
            field=models.CharField(default='', max_length=200),
        ),
    ]
