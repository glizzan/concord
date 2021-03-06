# Generated by Django 2.2.13 on 2020-10-09 16:05

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0006a_auto_20201009_1605'),
        ('conditionals', '0006_conditionmanager'),
    ]

    operations = [
        migrations.AddField(
            model_name='community',
            name='governor_condition',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='communities_community_governor_conditioned', to='conditionals.ConditionManager'),
        ),
        migrations.AddField(
            model_name='community',
            name='owner_condition',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='communities_community_owner_conditioned', to='conditionals.ConditionManager'),
        ),
        migrations.AddField(
            model_name='defaultcommunity',
            name='governor_condition',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='communities_defaultcommunity_governor_conditioned', to='conditionals.ConditionManager'),
        ),
        migrations.AddField(
            model_name='defaultcommunity',
            name='owner_condition',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='communities_defaultcommunity_owner_conditioned', to='conditionals.ConditionManager'),
        ),
    ]
