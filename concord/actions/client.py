from typing import Tuple, Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.contrib.auth.models import User

from concord.actions.models import Action, ActionContainer, TemplateModel
from concord.actions import state_changes as sc
from concord.actions.customfields import Template


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
            model_class = ct.model_class()
            self.target = model_class.objects.get(id=target_pk)
        else:
            raise BaseException("Must supply target or target_pk and target_ct.")

    def refresh_target(self):
        self.target.refresh_from_db()

    def validate_target(self):
        if not self.target:
            raise BaseException("Target is required")

    def change_is_valid(self, change):
        # FIXME: we don't call this from anywhere, but we should probably validate the change before creating the
        # action, not after
        if change.validate(self.actor, self.target):
            return True
        return False

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

    def create_mock_action_from_client(self):
        """Typically used to create trigger actions"""
        return Mockaction(actor=self.actor, target=self.target)

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

    def get_container_given_trigger_action(self, action=None, action_pk=None):
        """Given the apply_template trigger action that created a container, get the associated container."""
        if not action and not action_pk:
            raise ValueError("Must supply action or action_pk parameter")
        action_pk = action_pk if action_pk else action.pk
        containers = ActionContainer.objects.filter(trigger_action_pk=action_pk)
        if containers:
            return containers[0]

    def get_container_data(self, container_pk=None, container=None):
        """Gets data associated with actions inside a container. Note that this is not strictly read only.
        FIXME: reformat Container model to save most recent action data, so we don't need to re-run 
        process_actions"""
        if not container_pk and not container:
            raise ValueError("Must supply container_pk or container to get_container_data")
        container = container if container else self.get_container_given_pk(pk=container_pk)
        return container.get_action_data()

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

    def create_action_container(self, action_list, trigger_action=None):
        """Takes in a list of Mock Actions generated using mock mode for this or other clients.  """
        container, log = Template(action_list=action_list).apply_template(trigger_action=trigger_action)
        return container, log

    def retry_action_container(self, container_pk, test=False):
        """Retries processing the actions in a given container.  If test is true, does not commit the actions."""
        container = ActionContainer.objects.get(pk=container_pk)
        status = container.commit_actions(test=test)
        return container, status

    def take_action(self, action=None, pk=None):
        """Helper method to take an action (or, usually, retry taking an action) from the client."""
        if not action and not pk:
            print("Warning: take_action called with neither action nor pk")
        if action:
            action.take_action()
        else:
            action = self.get_action_given_pk(pk=pk)
            action.take_action()


class TemplateClient(BaseClient):

    # Get

    def get_template(self, pk):
        """Gets template with supplied pk or returns None."""
        queryset = TemplateModel.objects.filter(pk=pk)
        if queryset:
            return queryset[0]

    def get_templates(self):
        """Gets all templates in DB."""
        return TemplateModel.objects.all()

    def get_templates_for_scope(self, scope):
        """Gets template in the given scope."""
        # FIXME: need to make scopes an arrayfield (which requires switching Concord default backend to postgres)
        # or find a way to more easily search for scope (I guess maybe could have models only have one scope?)
        templates = []
        for template in TemplateModel.objects.all():
            if scope in template.get_scopes():
                templates.append(template)
        return templates

    def get_templates_for_owner(self, owner):
        ...

    # Create

    def create_template(self, name, user_description, scopes, template_data):
        ...

    # State changes

    def apply_template(self, template_model_pk, supplied_fields=None):
        """This is a weird state change, because it doesn't directly change the state of a permissioned model.
        Instead it creates an ActionContainer, copying the template field of the template model specified with
        template_model_pk.  If the Actions in the ActionContainer all successfully pass the permissions/conditions
        pipeline, only then are the state changes implemented.  So setting this permission doesn't actually
        give people the ability to apply templates - only prevents it.
        
        To minimize frustration for users, we circumvent the pipeline and automatically allow anyone to try to apply
        templates (since they still need to pass the individual actions that make up the template.)

        # TODO: refactor - should this be a state change at all?
        """
        change = sc.ApplyTemplateStateChange(template_model_pk=template_model_pk, supplied_fields=supplied_fields)
        action, result = self.create_and_take_action(change)
        if action.resolution.foundational_status == "not tested" and action.resolution.status == "rejected":
            # ^^ don't want to override a foundational rejection
            result = action.implement_action()
            action.resolution.log = "Overrode permissions pipeline"
        return action, result

    def edit_template(self, template_pk, name=None, user_description=None, scopes=None, template_data=None):
        if not Name and not user_description and not scopes and not template_data:
            raise ValueError("When editing template, must supply some data to change")
        ...

    def delete_template(self, template_pk):
        ...