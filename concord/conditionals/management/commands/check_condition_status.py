from django.utils import timezone

from django.core.management.base import BaseCommand, CommandError
import django.dispatch


retry_action_signal = django.dispatch.Signal(providing_args=["instance"])


class Command(BaseCommand):
    help = 'Checks conditions to see if their status has changed and, if status has changed, re-runs associated actions.'


    def handle(self, *args, **options):

        from concord.conditionals.models import ApprovalCondition, VoteCondition
        for condition_class in [ApprovalCondition, VoteCondition]:  # FIXME: we need a helper method for this

            print("Running for condition class ", condition_class)

            for instance in condition_class.objects.all():

                print("Running for isntance: ", instance)

                if instance.has_timeout:

                    if timezone.now() > instance.get_timeout():  

                        print("Sending signal!") 

                        # TODO: Right now, we're sending a signal for every condition that has ever finished. It would be 
                        # nice to have some archiving mechanism.
                        retry_action_signal.send(sender=condition_class, instance=instance, created=False) 


        