"""Client for making changes to models in Action.models, along with the BaseClient which other packages inherit
from."""

from typing import Tuple, Any
from collections import namedtuple
import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.core.exceptions import ObjectDoesNotExist

from concord.actions.models import Action, TemplateModel
from concord.utils.lookups import get_all_permissioned_models, get_all_state_changes
from concord.utils.pipelines import action_pipeline
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
    raise_error_if_failed = False
    app_name = None

    def __init__(self, actor=None, target=None):
        self.actor = actor
        self.target = target

    def __getattribute__(self, name):
        """Helper method to help debug when getattribute is erroring, switch True to False
        to silence."""
        if False:
            try:
                return object.__getattribute__(self, name)
            except Exception as error:
                print(f"Error when trying __getattribute {name} on {self}: {error} ")
                raise error
        else:
            return object.__getattribute__(self, name)

    def __getattr__(self, name):
        """Getattr is only called if __getattribute__ fails with an attribute error. If you expect this to be called but
        it isn't, check that however you're calling it will fail otherwise."""
        state_change_function = self.get_state_change_function(name)
        if state_change_function:
            return state_change_function
        raise AttributeError(f"No attribute {name} on {self}")

    def match_state_change_app(self, state_change):
        if state_change.__name__ == "BaseStateChange":
            return False
        if state_change.__module__[:8] == "concord.":
            if state_change.__module__[:19] == "concord.communities":
                return True
            return f".{self.app_name}." in state_change.__module__
        return f"{self.app_name}." in state_change.__module__

    def get_state_change_function(self, name):
        """This method, which should be called only within getattr by the client, allows us to instantiate state
        changes and create/take actions with them from the client without having to explicitly define methods for
        each one. The function returns expects as args the dictionary of parameters that need to be passed on to
        the state change, and the client that will be used to create and take the action."""
        if self.app_name:
            for state_change in get_all_state_changes():
                if self.match_state_change_app(state_change):
                    change_name = state_change.change_description(capitalize=False).strip(" ").replace(" ", "_")
                    if change_name == name:
                        def state_change_function(**kwargs):
                            proposed = kwargs.get("proposed", None)
                            change = state_change(**kwargs)
                            return self.create_and_take_action(change, proposed)
                        return state_change_function

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
            if self.target.__class__.__name__ == "Action":
                print("Warning: using an action as target, this should only be done in rare circumstances")
            else:
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
        result = change.validate_state_change(self.actor, self.target)
        if result:
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

    def create_action(self, change):
        """Create an Action object using the change object passed in as well as the actor and target already
        set on the Client. Called by clients when making changes to state.

        If the mode set on the client is "Mock", creates a mock action intead and returns it. Mocks are mostly
        used by Templates."""

        if self.mode == "mock":
            from concord.actions.utils import MockAction
            return MockAction(actor=self.actor, target=self.target, change=change)

        self.validate_target()
        self.validate_actor()

        if self.change_is_valid(change):
            return Action.objects.create(actor=self.actor, target=self.target,
                                         change=change)
        else:
            logging.info(f"Invalid action by {self.actor} on target {self.target} with change type {change}: "
                         + f"{change.validation_error_message}")
            InvalidAction = namedtuple('InvalidAction', ['error_message', 'status'])
            return InvalidAction(error_message=change.validation_error_message, status="invalid")

    def take_action(self, action, proposed=None):
        """If the action is a mock, invalid, or proposed, return without taking it, otherwise take the
        action."""
        if self.mode == "mock":
            return action

        if action.status == "invalid":
            if self.raise_error_if_failed:
                raise ValueError(message=action.error_message)
            return action, None

        if proposed:
            action.status = proposed
            action.save()
            return action, None

        action.status = "taken"
        result = action_pipeline(action)
        if action.status == "rejected" and self.raise_error_if_failed:
            raise ValueError(message=action.get_logs())
        return action, result

    def try_target_refresh(self, response):
        if isinstance(response, tuple) and response[0].status == "implemented":
            try:
                self.target.refresh_from_db()
            except AttributeError:
                pass
            except ObjectDoesNotExist:
                pass

    def create_and_take_action(self, change, proposed=None):
        """Creates an action and takes it."""
        action = self.create_action(change)
        response = self.take_action(action, proposed)
        if not proposed:
            self.try_target_refresh(response)
        return response

    def get_object_given_model_and_pk(self, model, pk, include_actions=False):
        """Given a model string and a pk, returns the instance. Only works on Permissioned models."""
        for permissioned_model in get_all_permissioned_models():
            if permissioned_model.__name__.lower() == model.lower():
                return permissioned_model.objects.get(pk=pk)
        if include_actions:
            if model.lower() == "action":
                return Action.objects.get(pk=pk)

    def set_default_permissions(self, created_model):
        """Gets sidewide default permissions and sets those corresponding to the given model, using
        actor and target."""
        from concord.permission_resources.utils import set_default_permissions
        set_default_permissions(self.actor, created_model)

    # Write

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

    app_name = "actions"

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
        return [action for action in actions if action.resolved_through == "governing"]

    def get_owning_actions_given_target(self, target=None) -> QuerySet:
        """Gets the action history of a target, filtered to only include actions resolved through
        foundational permission. Similar to filtering foundational_actions, but includes non-foundational
        actions taken on targets with the foundational permission enabled."""
        actions = self.get_action_history_given_target(target)
        return [action for action in actions if action.resolved_through == "foundational"]

    # Indirect change of state

    def retake_action(self, action=None, pk=None):
        """Helper method to take an action (or, usually, retry taking an action) from the client."""
        if not action and not pk:
            logger.warn("Take_action called with neither action nor pk")
        action = action if action else self.get_action_given_pk(pk=pk)
        if action.status in ["created", "propose-vol"]:
            action.status = "taken"
        action_pipeline(action)
        return action


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

    app_name = "actions"

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

    def apply_template(self, template_model_pk=None, supplied_fields=None, **kwargs):
        """Applies a template to the target.  If any of the actions in the template is a foundational change,
        changes the state change object's attr to foundational so it goes through the foundational pipeline."""

        if self.mode == "mock":
            change = sc.ApplyTemplateStateChange(
                template_model_pk=template_model_pk, supplied_fields=supplied_fields,
                template_is_foundational=None, **kwargs)
            return self.create_and_take_action(change)

        template_model = TemplateModel.objects.get(pk=template_model_pk)
        change = sc.ApplyTemplateStateChange(template_model_pk=template_model_pk, supplied_fields=supplied_fields,
                                             template_is_foundational=template_model.has_foundational_actions, **kwargs)

        action, result = self.create_and_take_action(change)
        if action.status == "invalid":
            return action, None

        description = template_model.get_template_breakdown(trigger_action=action, supplied_field_data=supplied_fields)
        action.template_info = description
        action.save()
        return action, result

