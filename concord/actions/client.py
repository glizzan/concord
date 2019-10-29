from typing import Tuple, Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.contrib.auth.models import User

from concord.actions.models import Action
from concord.actions import state_changes as sc


class BaseClient(object):
    """
    Contains behavior needed for all clients.
    """

    def __init__(self, actor=None, target=None, system=False):
        """Initialize client.  Can only initialize without an actor if running as system."""
        # FIXME: still don't like this hack
        if system:
            from django.contrib.auth.models import User
            self.actor = User.objects.get_or_create(username="system")
        elif actor is None:
            raise BaseException("Actor is required")
        self.actor = actor
        self.target = target

    def set_target(self, target):
        self.target = target

    def refresh_target(self):
        self.target.refresh_from_db()

    def validate_target(self):
        if not self.target:
            raise BaseException("Target is required")

    def optionally_overwrite_target(self, target):
        self.target = target if target else self.target
        self.validate_target()

    def set_actor(self, actor):
        self.actor = actor

    def create_and_take_action(self, change):
        self.validate_target()
        action = Action.objects.create(actor=self.actor, target=self.target, 
            change=change)
        return action.take_action()
    
    # Writing

    def change_owner_of_target(self, new_owner) -> Tuple[int, Any]:
        new_owner_content_type = ContentType.objects.get_for_model(new_owner)
        change = sc.ChangeOwnerStateChange(new_owner_content_type=new_owner_content_type.id, 
            new_owner_id=new_owner.id)
        return self.create_and_take_action(change)

    def enable_foundational_permission(self) -> Tuple[int, Any]:
        change = sc.EnableFoundationalPermissionStateChange()
        return self.create_and_take_action(change)

    def disable_foundational_permission(self) -> Tuple[int, Any]:
        change = sc.DisableFoundationalPermissionStateChange()
        return self.create_and_take_action(change)

    def enable_governing_permission(self) -> Tuple[int, Any]:
        change = sc.EnableGoverningPermissionStateChange()
        return self.create_and_take_action(change)

    def disable_governing_permission(self) -> Tuple[int, Any]:
        change = sc.DisableGoverningPermissionStateChange()
        return self.create_and_take_action(change)


class ActionClient(BaseClient):

    # Read only

    def get_action_given_pk(self, pk):
        actions = Action.objects.filter(pk=pk)
        if actions:
            return actions[0]
        return None

    def get_action_history_given_target(self, target=None) -> QuerySet:
        self.optionally_overwrite_target(target=target)
        content_type = ContentType.objects.get_for_model(self.target)
        return Action.objects.filter(content_type=content_type.id,
            object_id=self.target.id)

    def get_action_history_given_actor(self, actor) -> QuerySet:
        return Action.objects.filter(actor=actor)

    def get_foundational_actions_given_target(self, target=None) -> QuerySet:
        self.optionally_overwrite_target(target=target)
        actions = self.get_action_history_given_target(self.target)
        changes = sc.foundational_changes()
        foundational_actions = []
        for action in actions:
            if action.change.get_change_type() in changes:
                foundational_actions.append(action)
        return foundational_actions

    def get_governing_actions_given_target(self, target=None) -> QuerySet:
        self.optionally_overwrite_target(target=target)
        actions = self.get_action_history_given_target(self.target)
        governing_actions = []
        for action in actions:
            if action.resolution.resolved_through == "governing":
                governing_actions.append(action)
        return governing_actions

    def get_owning_actions_given_target(self, target=None) -> QuerySet:
        self.optionally_overwrite_target(target=target)
        actions = self.get_action_history_given_target(self.target)
        owning_actions = []
        for action in actions:
            if action.resolution.resolved_through == "foundational":
                owning_actions.append(action)
        return owning_actions