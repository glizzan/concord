# Generated by Django 2.2.4 on 2020-05-31 18:56

import concord.actions.customfields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('permission_resources', '0002_permissionsitem_anyone'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionsitem',
            name='condition',
            field=concord.actions.customfields.TemplateField(default=concord.actions.customfields.Template, system=True),
        ),
        migrations.DeleteModel(
            name='Template',
        ),
    ]
