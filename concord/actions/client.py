from typing import Tuple, Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet

from concord.actions.models import create_action, Action
from concord.actions import state_changes as sc


class BaseClient(object):
    """
    Contains behavior needed for all clients.
    """

    def __init__(self, actor, target=None):
        self.actor = actor
        self.target = target

    def set_target(self, target):
        self.target = target

    def set_actor(self, actor):
        self.actor = actor

    def create_and_take_action(self, change):
        if not self.target:
            raise BaseException("Target is required")
        action = create_action(change=change, target=self.target, actor=self.actor)
        return action.take_action()
    
    # Writing

    def change_owner_of_target(self, new_owner: str, new_owner_type: str) -> Tuple[int, Any]:
        change = sc.ChangeOwnerStateChange(new_owner=new_owner, 
            new_owner_type=new_owner_type)
        return self.create_and_take_action(change)

    def enable_foundational_permission(self) -> Tuple[int, Any]:
        change = sc.EnableFoundationalPermissionStateChange()
        return self.create_and_take_action(change)

    def disable_foundational_permission(self) -> Tuple[int, Any]:
        change = sc.DisableFoundationalPermissionStateChange()
        return self.create_and_take_action(change)


class ActionClient(BaseClient):

    # Read only

    def get_action_history_given_target(self, target) -> QuerySet:
        content_type = ContentType.objects.get_for_model(target)
        return Action.objects.filter(content_type=content_type.id,
            object_id=target.id)

    def get_action_history_given_actor(self, actor: str) -> QuerySet:
        return Action.objects.filter(actor=actor)



