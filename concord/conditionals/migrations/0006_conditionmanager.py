# Generated by Django 2.2.13 on 2020-10-09 15:58

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('conditionals', '0005_consensuscondition'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConditionManager',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('foundational_permission_enabled', models.BooleanField(default=False)),
                ('governing_permission_enabled', models.BooleanField(default=True)),
                ('community', models.IntegerField()),
                ('conditions', models.TextField()),
                ('set_on', models.CharField(choices=[('permission', 'Permission'), ('owner', 'Owner'), ('governor', 'Governor')], max_length=10)),
                ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conditionmanager_models', to=settings.AUTH_USER_MODEL)),
                ('owner_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conditionals_conditionmanager_owned_objects', to='contenttypes.ContentType')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]