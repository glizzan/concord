# Generated by Django 2.2.4 on 2020-05-09 20:07

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='VoteCondition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('foundational_permission_enabled', models.BooleanField(default=False)),
                ('governing_permission_enabled', models.BooleanField(default=True)),
                ('action', models.IntegerField()),
                ('yeas', models.IntegerField(default=0)),
                ('nays', models.IntegerField(default=0)),
                ('allow_abstain', models.BooleanField(default=True)),
                ('abstains', models.IntegerField(default=0)),
                ('require_majority', models.BooleanField(default=False)),
                ('publicize_votes', models.BooleanField(default=False)),
                ('voted', models.CharField(default='[]', max_length=500)),
                ('voting_starts', models.DateTimeField(default=django.utils.timezone.now)),
                ('voting_period', models.IntegerField(default=168)),
                ('owner_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conditionals_votecondition_owned_objects', to='contenttypes.ContentType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ConditionTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('foundational_permission_enabled', models.BooleanField(default=False)),
                ('governing_permission_enabled', models.BooleanField(default=True)),
                ('conditioned_object_id', models.PositiveIntegerField()),
                # ('condition_data', concord.conditionals.customfields.ConditionDataField(default=concord.conditionals.customfields.UnvalidatedConditionData)),
                ('conditioned_object_content_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
                ('owner_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conditionals_conditiontemplate_owned_objects', to='contenttypes.ContentType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ApprovalCondition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('foundational_permission_enabled', models.BooleanField(default=False)),
                ('governing_permission_enabled', models.BooleanField(default=True)),
                ('action', models.IntegerField()),
                ('approved', models.BooleanField(blank=True, null=True)),
                ('self_approval_allowed', models.BooleanField(default=False)),
                ('owner_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conditionals_approvalcondition_owned_objects', to='contenttypes.ContentType')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
