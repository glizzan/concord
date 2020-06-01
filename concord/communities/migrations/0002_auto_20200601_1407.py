# Generated by Django 2.2.4 on 2020-06-01 14:07

import concord.actions.customfields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='community',
            name='governor_condition',
            field=concord.actions.customfields.TemplateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='community',
            name='owner_condition',
            field=concord.actions.customfields.TemplateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='defaultcommunity',
            name='governor_condition',
            field=concord.actions.customfields.TemplateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='defaultcommunity',
            name='owner_condition',
            field=concord.actions.customfields.TemplateField(blank=True, null=True),
        ),
    ]