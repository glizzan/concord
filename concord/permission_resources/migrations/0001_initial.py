# Generated by Django 2.1.2 on 2018-10-19 20:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='PermissionsItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actor', models.CharField(max_length=200)),
                ('action_type', models.CharField(max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='PermissionsResource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_id', models.PositiveIntegerField()),
                ('content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
            ],
        ),
        migrations.AddField(
            model_name='permissionsitem',
            name='resource',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='permission_resources.PermissionsResource'),
        ),
    ]
