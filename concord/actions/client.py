from typing import Tuple, Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.contrib.auth.models import User

from concord.actions.models import Action, ActionContainer
from concord.actions import state_changes as sc


class BaseClient(object):
    """
    Contains behavior needed for all clients.
    """

    mode = "default"

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

    def set_target(self, target=None, target_pk=None, target_ct=None):
        if target:
            self.target = target
        elif target_pk and target_ct:
            ct = ContentType.objects.get_for_id(target_ct)
            model_class = ct._model_class()
            self.target = model_class.objects.get(id=target_pk)
        else:
            raise BaseException("Must supply target or target_pk and target_ct.")

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
        """This method is called by clients when making changes to state.  In rare cases, we'll 
        call to create Mocks (used to run through permissions.py just to determine if a user has
        permission to do an action) or Drafts, which are managed by ActionContainers."""

        if self.mode == "mock":     # typically used when checking permissions to limit what's displayed
            from concord.actions.utils import MockAction
            return MockAction(change=change, actor=self.actor, target=self.target)

        elif self.mode == "draft":  # typically used in Action Container
            return Action.objects.create(actor=self.actor, target=self.target, 
                    change=change)
        else:
            
            self.validate_target()

            action = Action.objects.create(actor=self.actor, target=self.target, 
                    change=change)
            return action.take_action()

    # Permissioned Reading

    def get_target_data(self, fields_to_include=None):
        change = sc.ViewChangelessStateChange(fields_to_include=fields_to_include)
        return self.create_and_take_action(change)

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
        print(f"Warning: tried to get action {pk} that wasn't in database")
        return None

    def get_container_given_pk(self, pk):
        containers = ActionContainer.objects.filter(pk=pk)
        if containers:
            return containers[0]
        print(f"Warning: tried to get container {pk} that wasn't in database")
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

    # Indirect change of state

    def create_action_container(self, action_list):
        """Takes in a list of Mock Actions generated using mock mode for this or other clients.  """
        container = ActionContainer.objects.create()
        container.initialize_action_info(action_list=action_list)
        return container

    def retry_action_container(self, container_pk, test=True):
        """Retries processing the actions in a given container.  If test is true, does not commit the actions."""
        container = ActionContainer.objects.get(pk=container_pk)
        container.commit_actions(test=test)
        return container

    def take_action(self, action=None, pk=None):
        """Helper method to take an action (or, usually, retry taking an action) from the client."""
        if not action and not pk:
            print("Warning: take_action called with neither action nor pk")
        if action:
            action.take_action()
        else:
            action = self.get_action_given_pk(pk=pk)
            action.take_action()