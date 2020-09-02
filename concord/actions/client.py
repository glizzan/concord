"""Client for making changes to models in Action.models, along with the BaseClient which other packages inherit
from."""

from typing import Tuple, Any
from collections import namedtuple
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet

from concord.actions.models import Action, TemplateModel
from concord.actions.utils import get_all_permissioned_models
from concord.actions import state_changes as sc


logger = logging.getLogger(__name__)


class BaseClient(object):
    """
    Contains behavior needed for all clients.

    Args:
        actor: User Model
            The User who the client is acting on behalf of. Optional, but required for many
            Client methods.
        target: PermissionedModel Model
            The target that the change will be implemented on. Optional, but required for many
            Client methods.
    """

    is_client = True
    mode = "default"

    def __init__(self, actor=None, target=None):
        self.actor = actor
        self.target = target

    def set_target(self, target=None, target_pk=None, target_ct=None):
        """Sets target of the client. Accepts either a target model or the target's pk and ct and fetches,
        in which case it fetches the model from the Database. Target must be a permissioned model."""
        if target:
            self.target = target
        elif target_pk and target_ct:
            content_type = ContentType.objects.get_for_id(target_ct)
            model_class = content_type.model_class()
            self.target = model_class.objects.get(id=target_pk)
        else:
            raise BaseException("Must supply target or target_pk and target_ct.")
        if not hasattr(self.target, "is_permissioned_model") or not self.target.is_permissioned_model:
            raise BaseException(f"Target {self.target} must be a permissioned model.")

    def get_target(self):
        """Gets the target of the client."""
        return self.target

    def refresh_target(self):
        """Re-populates model from database."""
        self.target.refresh_from_db()

    def validate_target(self):
        """Helper method to check whether or not we've got a target and that it's a permissioned model."""
        if not self.target:
            raise BaseException("Target is required")
        if not hasattr(self.target, "is_permissioned_model") or not self.target.is_permissioned_model:
            raise BaseException(f"Target {self.target} must be a permissioned model.")

    def change_is_valid(self, change):
        """Returns True if the change passed in is valid, given the Client's actor and target, and False if
        it is not."""
        if change.validate(self.actor, self.target):
            return True
        return False

    def optionally_overwrite_target(self, target):
        """Helper method that takes in a target, which may be None, and overwrites the existing target only if
        not None."""
        self.target = target if target else self.target
        self.validate_target()

    def set_actor(self, actor):
        """Sets actor."""
        self.actor = actor

    def validate_actor(self):
        """Helper method to check whether or not we've got an actor and whether they're a user."""
        if not self.actor:
            raise BaseException("An actor is required")
        if not hasattr(self.actor, "is_authenticated") or not self.actor.is_authenticated:
            raise BaseException(f"Actor {self.actor} must be an authenticated User.")

    def create_and_take_action(self, change):
        """Create an Action object using the change object passed in as well as the actor and target already
        set on the Client. Called by clients when making changes to state.

        If the mode set on the client is "Mock", creates a mock action intead and returns it. Mocks are mostly
        used by Templates.
        """

        if self.mode == "mock":
            from concord.actions.utils import MockAction
            return MockAction(actor=self.actor, target=self.target, change=change)

        self.validate_target()
        self.validate_actor()

        if self.change_is_valid(change):
            action = Action.objects.create(actor=self.actor, target=self.target,
                                           change=change)
            return action.take_action()
        else:
            logging.info(f"Invalid action by {self.actor} on target {self.target} with change type {change}: "
                         + f"{change.validation_error.message}")
            InvalidAction = namedtuple('InvalidAction', ['error_message', 'status'])
            return InvalidAction(error_message=change.validation_error.message, status="invalid"), None

    def get_object_given_model_and_pk(self, model, pk):
        """Given a model string and a pk, returns the instance. Only works on Permissioned models."""
        for permissioned_model in get_all_permissioned_models():
            if permissioned_model.__name__.lower() == model:
                return permissioned_model.objects.get(pk=pk)

    # State Change methods

    def get_target_data(self, fields_to_include=None):
        """Gets information about the target after passing request through permissions pipeline. Supply
        fields_to_include, a list of field names as strings, to limit the data requested, otherwise returns
        all fields."""
        change = sc.ViewStateChange(fields_to_include=fields_to_include)
        return self.create_and_take_action(change)

    # Writing

    def change_owner_of_target(self, new_owner) -> Tuple[int, Any]:
        """Changes the owner of the Client's target.

        Args:
            new_owner: descendant of base Community Model
                The new owner the target will be transferred to.
        """
        new_owner_content_type = ContentType.objects.get_for_model(new_owner)
        change = sc.ChangeOwnerStateChange(new_owner_content_type=new_owner_content_type.id,
                                           new_owner_id=new_owner.id)
        return self.create_and_take_action(change)

    def enable_foundational_permission(self) -> Tuple[int, Any]:
        """Enables the foundational permission on a target. This overrides all specific permissions and
        governing permissions and requires changes to the target to be made by owners. Foundational
        permission is typically disabled."""
        change = sc.EnableFoundationalPermissionStateChange()
        return self.create_and_take_action(change)

    def disable_foundational_permission(self) -> Tuple[int, Any]:
        """Disables the foundational permission on a target. Foundational permission is typically disabled."""
        change = sc.DisableFoundationalPermissionStateChange()
        return self.create_and_take_action(change)

    def enable_governing_permission(self) -> Tuple[int, Any]:
        """Enables the governing permission on a target. This allows anyone who is a governor to take any
        non-foundational action on the target. Governing permission is typically enabled."""
        change = sc.EnableGoverningPermissionStateChange()
        return self.create_and_take_action(change)

    def disable_governing_permission(self) -> Tuple[int, Any]:
        """Disables the governing permission on a target. This prevents governors from taking actions on the
        target unless they're granted specific permissions. Governing permission is typically enabled."""
        change = sc.DisableGoverningPermissionStateChange()
        return self.create_and_take_action(change)


class ActionClient(BaseClient):
    """The ActionClient provides access to Action and ActionContainer models.

    Args:
        actor: User Model
            The User who the client is acting on behalf of. Optional, but required for many
            Client methods.
        target: PermissionedModel Model
            The target that the change will be implemented on. Optional, but required for many
            Client methods.
    """

    # Read only

    def get_action_given_pk(self, pk):
        """Takes a pk (int) and returns the Action associated with it."""
        actions = Action.objects.filter(pk=pk)
        if actions:
            return actions[0]
        logging.warning(f"Tried to retrieve Action not in database: pk {pk}")
        return None

    def get_action_history_given_target(self, target=None) -> QuerySet:
        """Gets the action history of a target. Accepts a target model passed in or, if no target is passed in,
        uses the target currently set on the client."""
        self.optionally_overwrite_target(target=target)
        content_type = ContentType.objects.get_for_model(self.target)
        return Action.objects.filter(content_type=content_type.id, object_id=self.target.id)

    def get_action_history_given_actor(self, actor=None) -> QuerySet:
        """Gets the action history of an actor. Accepts an User model passed in or, if no actor is passed in,
        uses the actor currently set on the client."""
        actor = actor if actor else self.actor
        return Action.objects.filter(actor=actor)

    def get_foundational_actions_given_target(self, target=None) -> QuerySet:
        """Gets the action history of a target, filtered to include only foundational changes."""
        actions = self.get_action_history_given_target(target)
        from concord.actions.utils import get_all_foundational_state_changes
        changes = get_all_foundational_state_changes()
        return [action for action in actions if action.change.get_change_type() in changes]

    def get_governing_actions_given_target(self, target=None) -> QuerySet:
        """Gets the action history of a target, filtered to only include actions resolved via the
        governing permission."""
        actions = self.get_action_history_given_target(target)
        return [action for action in actions if action.resolution.resolved_through == "governing"]

    def get_owning_actions_given_target(self, target=None) -> QuerySet:
        """Gets the action history of a target, filtered to only include actions resolved through
        foundational permission. Similar to filtering foundational_actions, but includes non-foundational
        actions taken on targets with the foundational permission enabled."""
        actions = self.get_action_history_given_target(target)
        return [action for action in actions if action.resolution.resolved_through == "foundational"]

    # Indirect change of state

    def take_action(self, action=None, pk=None):
        """Helper method to take an action (or, usually, retry taking an action) from the client."""
        if not action and not pk:
            logger.warn("Take_action called with neither action nor pk")
        action = action if action else self.get_action_given_pk(pk=pk)
        action.take_action()


class TemplateClient(BaseClient):
    """The TemplateClient provides access to the TemplateModel model.

    Args:
        actor: User Model
            The User who the client is acting on behalf of. Optional, but required for many
            Client methods.
        target: PermissionedModel Model
            The target that the change will be implemented on. Optional, but required for many
            Client methods.
    """

    # Read-only methods

    def get_template(self, pk):
        """Gets template with supplied pk or returns None."""
        queryset = TemplateModel.objects.filter(pk=pk)
        return queryset[0] if queryset else None

    def get_templates(self):
        """Gets all templates in database."""
        return TemplateModel.objects.all()

    def get_templates_for_scope(self, scope):
        """Gets template in the given scope."""
        templates = []
        for template in TemplateModel.objects.all():
            if scope in template.get_scopes():
                templates.append(template)
        return templates

    # State changes

    def apply_template(self, template_model_pk, supplied_fields=None):
        """Applies a template to the target.  If any of the actions in the template is a foundational change,
        changes the state change object's attr to foundational so it goes through the foundational pipeline."""
        change = sc.ApplyTemplateStateChange(template_model_pk=template_model_pk, supplied_fields=supplied_fields)
        template_model = TemplateModel.objects.get(pk=template_model_pk)
        if template_model.has_foundational_actions:
            change.is_foundational = True
        if self.mode == "mock":
            return self.create_and_take_action(change)
        action, result = self.create_and_take_action(change)
        description = template_model.get_template_breakdown(trigger_action=action, supplied_field_data=supplied_fields)
        action.resolution.template_info = description
        action.save()
        return action, result
