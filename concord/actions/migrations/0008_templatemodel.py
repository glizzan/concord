# Generated by Django 2.2.4 on 2020-06-22 20:26

import concord.actions.customfields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('actions', '0007_auto_20200621_1646'),
    ]

    operations = [
        migrations.CreateModel(
            name='TemplateModel',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('foundational_permission_enabled', models.BooleanField(default=False)),
                ('governing_permission_enabled', models.BooleanField(default=True)),
                ('template_data', concord.actions.customfields.TemplateField(default=concord.actions.customfields.Template)),
                ('scopes', models.CharField(max_length=200)),
                ('name', models.CharField(max_length=90, unique=True)),
                ('user_description', models.CharField(max_length=500)),
                ('supplied_fields', models.CharField(max_length=500)),
                ('owner_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='actions_templatemodel_owned_objects', to='contenttypes.ContentType')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
