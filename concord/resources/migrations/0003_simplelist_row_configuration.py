# Generated by Django 2.2.4 on 2020-09-03 18:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0002_simplelist'),
    ]

    operations = [
        migrations.AddField(
            model_name='simplelist',
            name='row_configuration',
            field=models.TextField(default='{"content": {"required": true}}', verbose_name=list),
            preserve_default=False,
        ),
    ]
