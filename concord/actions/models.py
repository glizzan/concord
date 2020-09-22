"""Django models for Actions and Permissioned Models."""

import json
import logging

from django.db import models, DatabaseError
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

from concord.actions.utils import get_state_changes_settable_on_model
from concord.actions.text_utils import action_to_text
from concord.actions.customfields import ResolutionField, Resolution, StateChangeField, Template, TemplateField


logger = logging.getLogger(__name__)


class Action(models.Model):
    """Represents an action between an actor and a target.

    All changes of state that go through the permissions system must do so via
    an Action instance.

    Action instances must include information about the actor taking the action
    and the target of the action, among other information.
    """
    # Related fields
    actor = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    target = GenericForeignKey()

    # Change field
    change = StateChangeField()

    # Resolution field stores status & log info as well as details of how the action has been processed
    resolution = ResolutionField(default=Resolution)

    # Regular old attributes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_draft = models.BooleanField(default=False)

    # Basics

    def __str__(self):
        target = self.target if self.target else "deleted target"
        return f"Action {self.pk} '{self.change.description}' by {self.actor} on {target} ({self.status})"

    @property
    def status(self):
        """Gets status of Action from Resolution field."""
        return self.resolution.generate_status()

    def save(self, *args, **kwargs):
        """If action is live (is_draft is False) check that target and actor are set."""
        if not self.is_draft and self.status != "implemented":
            if self.target is None or self.actor is None:
                raise DatabaseError("Must set target and actor before sending or implementing an Action")
        return super().save(*args, **kwargs)  # Call the "real" save() method.

    def get_description(self):
        """Gets description of the action by reference to `change_types` set via change field, including the target."""
        return action_to_text(self)

    def get_targetless_description(self):
        """Gets description of the action by reference to `change_types` set via change field, without the target."""
        return action_to_text(self, with_target=False)

    # Steps of action execution

    def implement_action(self):
        """Perform an action defined by the Change object. Carries out its custom implementation using the actor
        and target."""
        if hasattr(self.change, "pass_action") and self.change.pass_action:
            result = self.change.implement(actor=self.actor, target=self.target, action=self)
        else:
            result = self.change.implement(actor=self.actor, target=self.target)
        self.resolution.meta_status = "implemented"
        logger.debug(f"{self} implemented")
        return result

    def take_action(self):
        """Runs the action through the permissions pipeline.  If waiting on a condition,
        triggers that condition.  If approved, implements action.

        Returns itself and, optionally, the result of implementing the action."""

        logger.info(f"Taking action {self.pk}: ({self.actor} {self.change.description} on {self.target})")

        if self.status in ["taken", "waiting"]:

            from concord.actions.permissions import has_permission
            self.resolution.refresh_pipeline_status()
            has_permission(action=self)

            if self.status == "waiting" and len(self.resolution.uncreated_conditions()) > 0:

                from concord.actions.utils import Client
                client = Client()
                for source_id in self.resolution.uncreated_conditions():
                    condition = client.Conditional.trigger_condition_creation_from_source_id(
                        action=self, source_id=source_id)
                    logger.info(f"Created condition {condition.pk} on action {self.pk} with source_id {source_id}")
                    self.resolution.condition_created(source_id)

        if self.status == "approved":
            result = self.implement_action()
            logger.debug(f"Result of action implementation {result}")

        logger.debug(f"Saving action {self.pk} with status {self.status}")
        self.save()

        return self, result if 'result' in locals() else None


class PermissionedModel(models.Model):
    """An abstract base class that represents permissions.

    `PermissionedModel` is an abstract base class from which all models using the permissions system
    should inherit.

    The `PermissionedModel` contains information about owners and their related permissions.
    """

    owner_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True,
                                           related_name="%(app_label)s_%(class)s_owned_objects")
    owner_object_id = models.PositiveIntegerField(blank=True, null=True)
    owner = GenericForeignKey('owner_content_type', 'owner_object_id')

    # Permission-related fields
    foundational_permission_enabled = models.BooleanField(default=False)
    governing_permission_enabled = models.BooleanField(default=True)

    # Creator (by default, all permissioned models have a creator field)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True, related_name='%(class)s_models')

    is_permissioned_model = True

    class Meta:
        abstract = True

    def get_name(self):
        """Gets name of Model. By default, gets string representation."""
        return self.__str__

    def get_owner(self):
        """Gets owner of the permissioned model.

        All permissioned models have an owner.
        """
        return self.owner

    def get_content_type(self):
        """Gets content type of the model.

        The content type is helpful since `PermissionedModels` may be subclassed into a variety
        of other models."""
        return ContentType.objects.get_for_model(self).pk

    def get_unique_id(self):
        """Gets a unique ID for the model, consisting of the content type and pk."""
        contentType = ContentType.objects.get_for_model(self)
        return "_".join([contentType.app_label, contentType.model, str(self.pk)])

    def get_actions(self):
        """Provides a helper method for getting actions.

        Returns all actions targeting the instance of the subclass which has inherited from
        `PermissionedModel`."""
        from concord.actions.utils import Client
        client = Client()
        return client.Action.get_action_history_given_target(target=self)

    def get_nested_objects(self):
        """Gets objects that the model is nested within.

        Nested objects are often things like the owner of instance or, for example,
        a forum that a post is posted within.

        Called by the permissions pipeline in `permissions.py`.
        """
        return []

    def get_serialized_field_data(self):  # NOTE: field_util?
        """Returns data that has been been serialized.

        By default, the readable attributes of a permissioned model are all fields specified on the
        model.  However, we cannot simply use `self._meta.get_fields()` since the field name is sometimes
        different than the attribute name, for instance with related fields that are called X but show
        up as X_set on the model."""

        # Generate list of fields
        fields = self._meta.get_fields()

        # Turn into dict
        data_dict = {}
        for field in fields:
            if field.__class__.__name__ in ["ManyToOneRel", "ManyToOneRelation"]:
                related_objects = getattr(self, field.name + "_set").all()
                serialized_field = [ro.pk for ro in related_objects]
            elif "content_type" in field.name:
                continue  # skip content_type fields used for gfks
            elif "object_id" in field.name:
                continue  # skip id field used in gfks
            else:
                serialized_field = getattr(self, field.name)
            if hasattr(serialized_field, "foundational_permission_enabled"):
                serialized_field = serialized_field.get_name()
            data_dict.update({field.name: serialized_field})

        return data_dict

    @classmethod
    def get_settable_state_changes(cls):
        """Returns a list of state_changes that can be set via permissions targeting this model.

        This may include some permissions where the *targets* are other than this model. For instance,
        if this object owns another object, we may have set permissions for actions targeting
        the owned object.
        """
        return get_state_changes_settable_on_model(cls)

    def save(self, *args, override_check=False, **kwargs):
        """Save permissions.

        There are two things happening here:

        1:  Subtypes of `BaseCommunity` are the *only* children of `PermissionedModel` that
            should be allowed to have a null owner.  We check that here and raise an error if
            a non-community model has null values for owner fields.

        2:  A permissioned model's save method can *only* be invoked by a descendant of
            `BaseStateChange`, on update (create is fine). For now, we inspect who is calling us, but
            there may be a better long-term solution.
        """

        # CHECK 1: only allow null owner for communities

        if not (self.owner and self.owner_content_type and self.owner_object_id):
            if not (hasattr(self, "is_community") and self.is_community):
                raise ValueError("Owner must be specified for model of type ", type(self))

        # CHECK 2: only invoke save method via descendant of BaseStateChange

        if not self.pk:  # Allow normal save on create, aka when no pk is defined.
            return super().save(*args, **kwargs)

        if override_check is True:  # or, if override_check is passed, allow normal save
            return super().save(*args, **kwargs)

        # Check all others for call by StateChange's 'implement' method.
        import inspect
        curframe = inspect.currentframe()
        caller = inspect.getouterframes(curframe, 5)
        calling_function_name = caller[1].function
        if calling_function_name == "implement":
            del curframe, caller
            return super().save(*args, **kwargs)

        # Accommodate overriding save on subclasses
        if calling_function_name == "save":
            calling_function_name = caller[2].function
            if calling_function_name == "implement":
                del curframe, caller
                return super().save(*args, **kwargs)

        raise BaseException("Save called incorrectly")


class TemplateModel(PermissionedModel):
    """The template model allows users to apply sets of actions to their communities."""

    template_data = TemplateField(default=Template, system=False)
    scopes = models.CharField(max_length=200)
    name = models.CharField(max_length=90, unique=True)
    user_description = models.CharField(max_length=500)
    supplied_fields = models.CharField(max_length=5000)

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"TemplateModel(pk={self.pk}, name={self.name}, user_description={self.user_description}, " + \
               f"supplied_fields={self.supplied_fields}, scopes={self.scopes}, template_data={self.template_data})"

    def get_scopes(self):
        """Gets list of scopes the template model applies to."""
        if self.scopes:
            return json.loads(self.scopes)
        return []

    def set_scopes(self, scopes):
        """Saves a list of scopes to the template model."""
        if not isinstance(scopes, list):
            raise TypeError(f"Scopes must be type list/array, not type {type(scopes)}")
        self.scopes = json.dumps(scopes)

    @property
    def has_foundational_actions(self):
        """Returns True if any of the actions in the action_list are foundational changes."""
        for action in self.template_data.action_list:
            if action.change.is_foundational:
                return True
        return False

    def get_template_breakdown(self, trigger_action=None, supplied_field_data=None):
        """Gets a breakdown of actions contained in the template, including data from trigger action and supplied
        field data if passed in."""
        if trigger_action and supplied_field_data:
            return self.template_data.programmatic_description(
                name=self.name, trigger_action=trigger_action, supplied_field_data=supplied_field_data,
                supplied_field_options=self.get_supplied_fields())
        else:
            return self.template_data.programmatic_description_uninstantiated(
                name=self.name, supplied_field_options=self.get_supplied_fields())

    def get_supplied_fields(self):
        """Get supplied fields as dictionary."""
        if self.supplied_fields:
            return json.loads(self.supplied_fields)
        return {}

    def get_supplied_form_fields(self):  # NOTE: field_util?
        """Loads template supplied fields and gets their forms, using field_helper.  Supplied
        fields typically have format like:

            "field_x": ["RoleListField", None]
            "field_y": ["IntegerField", { "maximum": 2 }]
        """

        from concord.actions.field_utils import field_helper

        form_fields = []

        for field_name, field_info in self.get_supplied_fields().items():

            overrides = {"field_name": field_name}
            if field_info[1] is not None:
                overrides.update(field_info[1])

            form_field = field_helper(field_info[0], overrides)
            form_fields.append(form_field)

        return form_fields
