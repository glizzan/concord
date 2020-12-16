from django.utils import timezone
from django.core.management.base import BaseCommand
import django.dispatch

from concord.utils.lookups import get_all_conditions


retry_action_signal = django.dispatch.Signal(providing_args=["instance"])


class Command(BaseCommand):
    help = 'Checks conditions to see if their status has changed and, if it has, re-runs associated actions.'

    def handle(self, *args, **options):

        for condition_class in get_all_conditions():

            for instance in condition_class.objects.all():

                if instance.has_timeout:

                    if timezone.now() > instance.get_timeout():

                        retry_action_signal.send(sender=condition_class, instance=instance, created=False)
