# Generated by Django 2.2.4 on 2020-06-01 13:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conditionals', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvalcondition',
            name='source_id',
            field=models.CharField(default=0, max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='votecondition',
            name='source_id',
            field=models.CharField(default=0, max_length=20),
            preserve_default=False,
        ),
    ]
