"""Django models for Actions and Permissioned Models."""

import json

from django.db import models, DatabaseError, transaction
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

from concord.actions.utils import get_state_change_objects_which_can_be_set_on_model
from concord.actions.customfields import ResolutionField, Resolution, StateChangeField


def get_default_resolution():
    """Helper function to set default resolution object in database for new actions."""
    return Resolution(status="draft")


class Action(models.Model):
    """Represents an action between an actor and a target.

    All changes of state that go through the permissions system must do so via
    an Action instance.

    Action instances must include information about the actor taking the action
    and the target of the action, among other information.
    """
    # Related fields
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey()
    container = models.PositiveIntegerField(blank=True, null=True)   

    # Change field
    change = StateChangeField()

    # Resolution field stores status & log info as well as details of how the action has been processed
    resolution = ResolutionField(default=get_default_resolution)

    # Regular old attributes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Basics

    def __str__(self):
        """Provides string describing the Action."""
        return f"{self.resolution.status} action {self.change.get_change_type()} by {self.actor} on {self.target} "

    def get_description(self):
        """Gets description of the action by reference to `change_types` set via change field, including the target."""
        if self.resolution.status == "implemented":
            description, target_preposition = self.change.description_past_tense(), self.change.get_preposition()
            return self.actor.username + " " + description + " " + target_preposition + " " + self.target.get_name()
        else:
            description, target_preposition = self.change.description_present_tense(), self.change.get_preposition()
            return self.actor.username + " asked to " + description + " " + target_preposition + " " + self.target.get_name()

    def get_targetless_description(self):
        """Gets description of the action by reference to `change_types` set via change field, without the target."""
        if self.resolution.status == "implemented":
            description, target_preposition = self.change.description_past_tense(), self.change.get_preposition()
            return self.actor.username + " " + description
        else:
            description, target_preposition = self.change.description_present_tense(), self.change.get_preposition()
            return self.actor.username + " asked to " + description

    def get_condition(self):
        """Gets condition set on the action, if one exists."""
        from concord.conditionals.client import PermissionConditionalClient
        pcc = PermissionConditionalClient(system=True)
        return pcc.get_condition_item_given_action(action_pk=self.pk)

    def get_condition_link(self):
        """Gets link to condition set on the action, if one exists.

        Returns link to condition formatted as display if successful;
        otherwise returns an empty string.
        """
        condition = self.get_condition()
        if condition:
            return f"<a href={condition.get_url()}>{condition.get_display_string()}</a>"
        return ""

    # Steps of action execution

    def validate_action(self):
        """Checks that an action is valid.

        Validation check is done by providing actor and target to the change
        itself, which implements its own custom logic.
        """
        is_valid = self.change.validate(actor=self.actor, target=self.target)
        if is_valid:
            self.resolution.status = "sent"
        else:
            self.resolution.status = "rejected"
            self.resolution.add_to_log(self.change.validation_error.message)
            delattr(self.change, "validation_error")

    def implement_action(self):
        """Perform an action by the change object.

        Carries out its custom implementation using the actor and target.
        """
        result = self.change.implement(actor=self.actor, target=self.target)
        self.resolution.status = "implemented"
        return result

    def take_action(self):
        """Take action by checking status and attempt the next step given that status.

        Returns result of the action.
        """
        current_result = None

        if self.resolution.status == "draft":
            self.validate_action()

        if self.resolution.status in ["sent", "waiting"]:
            from concord.actions.permissions import has_permission
            self = has_permission(action=self)

        if self.resolution.status == "approved" and not self.resolution.provisional:
            current_result = self.implement_action()

        self.save()  # Save action, may not always be needed

        return self, current_result


class ActionContainer(models.Model):
    """An `ActionContainer` is a tool for helping generate, process, and implement a set of actions
    as a cohesive group.  This is useful for user-facing templates as well as for system actions
    that are closely connected to each other and which users might see as a single action, for
    example "adding a user with role X to group Y". This might seem like one action to a user but would actually 
    be three: adding the role to the group, adding the user to the group, and adding the user to the role.
    """
    action_info = models.CharField(max_length=800, null=True, blank=True)  # Probably should be a custom field
    summary_status = models.CharField(max_length=20, default="drafted")
    is_open = models.BooleanField(default=True)

    def initialize_action_info(self, action_list):
        """Takes in a list of MockActions, which have typically just been checked using check_permissions_for_action_group.
        Creates actions in the database, giving them draft status, and records their pks here."""

        action_info = {}

        for count, action in enumerate(action_list):

            db_action = Action.objects.create(actor=action.actor, target=action.target, change=action.change,
                container=self.pk)

            action_info.update({ count: { "pk": db_action.pk , "status": {
                "overall": "draft", "validated": None, "permissions_checked": None, "implemented": None,
                "committed": None }, "log": None }})

        self.action_info = json.dumps(action_info)
        self.save()

    def process_actions(self):
        """Goes through actions in order and implements them, updating action_info with the results of various checks.  
        (Almost?) always called from within a transaction.atomic() block, so may not actually be committed to DB."""

        from concord.actions.permissions import has_permission

        action_info = json.loads(self.action_info)
        ok_to_commit = True

        for count in range(0, len(action_info)):

            count = str(count)

            action = Action.objects.get(pk=action_info[count]['pk'])

            # Check that the action is still valid
            is_valid = action.change.validate(actor=action.actor, target=action.target)  
            if not is_valid:
                action_info[count]["status"]["validated"] = False
                action_info[count]["log"] = action.change.validation_error.message
                ok_to_commit = False
                continue
            action_info[count]["validated"] = True 

            # Check that the action passes permissions
            changed_action = has_permission(action=action)
            if changed_action.resolution.status != "approved":
                action_info[count]["status"]["permissions_checked"] = False
                action_info[count]["log"] = action.resolution.log
                ok_to_commit = False
                continue
            action_info[count]["status"]["permissions_checked"] = True

            # Implement action 
            action.implement_action()
            action_info[count]["status"]["implemented"] = True
            action.save()

        return action_info, ok_to_commit

    def commit_actions(self, test=True):

        try:

            with transaction.atomic():

                action_info, ok_to_commit = self.process_actions()

                if not ok_to_commit or test:
                    raise DatabaseError()

                self.summary_status = "committed"
                self.is_open = False   # one the actions have all been committed, close container

        except DatabaseError as db_error:

            self.summary_status = "okay to commit" if ok_to_commit else "not okay to commit"

        self.action_info = json.dumps(action_info)
        self.save()


class PermissionedModel(models.Model):
    """An abstract base class that represents permissions.

    `PermissionedModel` is an abstract base class from which all models using the permissions system
    should inherit.

    The `PermissionedModel` contains information about owners and their related permissions.
    """
    owner_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_owned_objects",
        blank=True,
        null=True
    )
    owner_object_id = models.PositiveIntegerField(blank=True, null=True)
    owner = GenericForeignKey('owner_content_type', 'owner_object_id')

    # Permission-related fields
    foundational_permission_enabled = models.BooleanField(default=False)
    governing_permission_enabled = models.BooleanField(default=True)

    class Meta:
        abstract = True

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
        from concord.actions.client import ActionClient
        client = ActionClient(system=True, target=self)
        return client.get_action_history_given_target(target=self)

    def get_nested_objects(self):
        """Gets objects that the model is nested within.

        Nested objects are often things like the owner of instance or, for example,
        a forum that a post is posted within.

        Called by the permissions pipeline in `permissions.py`.
        """
        return []

    def get_serialized_field_data(self):
        """Returns data that has been been serialized.

        By default, the readable attributes of a permissioned model are all fields specified on the
        model.  However, we cannot simply use `self._meta.get_fields()` since the field name is sometimes
        different than the attribute name, for instance with related fields that are called, X but show
        up as X_set on the model.

        For now we're assuming this is going to be user-facing. Eventually we need to refactor the
        serialization done here, in the `state_change` serialization, and in the templates so it's all
        relying on a single set of utils for consistency's sake.
        """

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
                continue  # skip id field used in gfks (FIXME: this is very brittle)
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
        return get_state_change_objects_which_can_be_set_on_model(model_class=cls, app_name=cls._meta.app_label)

    def save(self, *args, override_check=False, **kwargs):
        """Save permissions.

        There are two things happening here:

        - 1:  Subtypes of `BaseCommunity` are the *only* children of `PermissionedModel` that
          should be allowed to have a null owner.  We check that here and raise an error if
          a non-community model has null values for owner fields.

        - 2:  A permissioned model's save method can *only* be invoked by a descendant of
          `BaseStateChange`, on update (create is fine). For now, we inspect who is calling us.
           *This is a hack.  Once we have better testing, we will enforce this via tests.*
        """

        # CHECK 1: only allow null owner for communities

        if not (self.owner and self.owner_content_type and self.owner_object_id):
            if not (hasattr(self, "is_community") and self.is_community):
                raise ValueError("Owner must be specified for model of type ", type(self))

        # CHECK 2: only invoke save method via descendant of BaseStateChange

        # Allow normal save on create.

        if not self.pk:
            return super().save(*args, **kwargs)  # Call the "real" save() method.

        # If override_check has been passed in by internal system, allow normal save.
        if override_check is True:
            return super().save(*args, **kwargs)  # Call the "real" save() method.

        # Check all others for call by StateChange.

        import inspect
        curframe = inspect.currentframe()
        caller = inspect.getouterframes(curframe, 5)
        calling_function_name = caller[1].function
        if calling_function_name == "implement":
            del curframe, caller
            return super().save(*args, **kwargs)  # Call the "real" save() method.
        # Hack to accommodate overriding save on subclasses
        if calling_function_name == "save":
            calling_function_name = caller[2].function
            if calling_function_name == "implement":
                del curframe, caller
                return super().save(*args, **kwargs)  # Call the "real" save() method.
        raise BaseException("Save called incorrectly")
