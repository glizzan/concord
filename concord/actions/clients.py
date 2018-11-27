from django.contrib.contenttypes.models import ContentType

from actions.models import create_action, Action
from actions import state_changes as sc


class BaseActionClient(object):

    def __init__(self, actor, target=None):
        self.actor = actor
        self.target = target

    # Read only

    def get_action_history_given_target(self, target):
        content_type = ContentType.objects.get_for_model(target)
        return Action.objects.filter(content_type=content_type.id,
            object_id=target.id)

    def get_action_history_given_actor(self, actor):
        return Action.objects.filter(actor=actor)

    # Writing

    def change_owner_of_target(self, new_owner, new_owner_type, target=None):
        change = sc.ChangeOwnerStateChange(new_owner=new_owner, new_owner_type=new_owner_type)
        return self.create_and_take_action(change, target)

    def set_target(self, target):
        self.target = target

    def set_actor(self, actor):
        self.actor = actor

    def check_target(self, target):
        """
        Because for now we're using the same client for everything, and the client 
        sometimes creates objects without needing a target or action, we need to
        check for the target before running an action.
        """
        if target:
            self.target = target
        if not self.target:
            raise BaseException("Target is required")

    def create_and_take_action(self, change, target):
        self.check_target(target)
        action = create_action(change=change, target=self.target, actor=self.actor)
        return action.take_action()
