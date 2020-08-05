"""Django models for Actions and Permissioned Models."""

import json
import logging

from django.db import models, DatabaseError, transaction
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

from concord.actions.utils import get_state_change_objects_which_can_be_set_on_model, ClientInterface, replace_fields
from concord.actions.customfields import (ResolutionField, Resolution, StateChangeField, TemplateField, 
                                          TemplateContextField, Template, TemplateContext)


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
    container = models.PositiveIntegerField(blank=True, null=True)   

    # Change field
    change = StateChangeField()

    # Resolution field stores status & log info as well as details of how the action has been processed
    resolution = ResolutionField(default=Resolution)

    # Regular old attributes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=15, default="created")
    is_draft = models.BooleanField(default=False)

    # Basics

    def __str__(self):
        return f"{self.status} action {self.change.description} by {self.actor} on {self.target} "

    def get_status(self):
        return "draft" if self.is_draft else self.status

    def save(self, *args, override_check=False, **kwargs):
        """
        If action is live (is_draft is False) check that target and actor are set.
        """
        if not self.is_draft:
            if self.target is None or self.actor is None:
                raise DatabaseError("Must set target and actor before sending or implementing an Action")
        return super().save(*args, **kwargs)  # Call the "real" save() method.     

    def get_description(self):
        """Gets description of the action by reference to `change_types` set via change field, including the target."""
        if self.status == "implemented":
            description, target_preposition = self.change.description_past_tense(), self.change.get_preposition()
            return self.actor.username + " " + description + " " + target_preposition + " " + self.target.get_name()
        else:
            description, target_preposition = self.change.description_present_tense(), self.change.get_preposition()
            return self.actor.username + " asked to " + description + " " + target_preposition + " " + self.target.get_name()

    def get_targetless_description(self):
        """Gets description of the action by reference to `change_types` set via change field, without the target."""
        if self.status == "implemented":
            description, target_preposition = self.change.description_past_tense(), self.change.get_preposition()
            return self.actor.username + " " + description
        else:
            description, target_preposition = self.change.description_present_tense(), self.change.get_preposition()
            return self.actor.username + " asked to " + description

    # Steps of action execution

    def implement_action(self):
        """Perform an action by the change object.

        Carries out its custom implementation using the actor and target.
        """
        if hasattr(self.change, "pass_action") and self.change.pass_action:
            logger.debug("Implementing action through pass_action workaround")
            result = self.change.implement(actor=self.actor, target=self.target, action=self)
        else:
            result = self.change.implement(actor=self.actor, target=self.target)
        self.status = "implemented"
        logger.debug(f"Action {self.pk} implemented")
        return result

    def take_action(self):
        """Runs the action through the permissions pipeline.  If waiting on a condition,
        triggers that condition.  If approved, implements action.  
        
        Returns itself and, optionally, the result of implementing the action.
        """

        logger.info(f"Taking action {self.pk}: ({self.actor} {self.change.description} on {self.target})")

        if self.status in ["created", "waiting"]:

            from concord.actions.permissions import has_permission
            self = has_permission(action=self)
            self.status = self.resolution.generate_status()

            if self.status == "waiting" and len(self.resolution.conditions) > 0:
                from concord.conditionals.client import ConditionalClient
                client = ConditionalClient(system=True)
                for source_id in self.resolution.conditions:
                    logger.info(f"Creating condition on action {self.pk} with source_id {source_id}")
                    client.trigger_condition_creation_from_source_id(action=self, source_id=source_id)

        if self.status == "approved":
            result = self.implement_action()
            logger.debug(f"Result of action implementation {result}")

        logger.debug(f"Saving action {self.pk} with status {self.status}")
        self.save()

        return self, result if 'result' in locals() else None


class ActionContainer(models.Model):
    """An `ActionContainer` is a tool for helping generate, process, and implement a set of actions
    as a cohesive group.  This is useful for user-facing templates as well as for system actions
    that are closely connected to each other and which users might see as a single action, for
    example "adding a user with role X to group Y". This might seem like one action to a user but could 
    actually be three: adding the role to the group, adding the user to the group, and adding the user to 
    the role.  ActionContainers allow us to trigger conditions for all of the actions at once, as well as
    wait on implementing any of the actions until all of them pass.
    
    ActionContainer stores the template information from the template that triggered it as well as context data
    specific to this particular application/implementation, for instance the pk of the action which triggered
    apply_template, and actions/results created by implemented the actions templates, as well as data for any
    user supplied fields.
    """

    template_data = TemplateField(default=Template)
    context = TemplateContextField(default=TemplateContext)
    trigger_action_pk = models.PositiveIntegerField(blank=True, null=True)
    status = models.CharField(max_length=500, blank=True, null=True)

    def __repr__(self):
        return f"ActionContainer(template_data={repr(self.template_data)}, context={repr(self.context)}, " + \
            f"status={self.status})"

    def __str__(self):
        return self.__repr__()

    @property
    def is_open(self):
        return False if self.status == "implemented" else True

    # Action processing methods

    def initialize(self, template_object, trigger_action, supplied_fields=None, make_actions_in_db=True):
        """Saves template object passed in to the template field, and initializes the context field with
        information passed in via the template."""
        logger.debug(f"Initializing container {self.pk}: trigger {trigger_action}, suppliedfields: {supplied_fields}")
        self.template_data = template_object
        self.context.initialize(template_object, trigger_action, supplied_fields)
        self.trigger_action_pk = trigger_action.pk
        if make_actions_in_db:
            self.context.create_actions_in_db(self.pk, self.template_data)

    def get_db_action(self, item):   
        """Gets action from db and processes it with replace_fields."""
        action = self.context.get_action_model_given_unique_id(item["unique_id"])
        mock_action = self.template_data.get_mock_action_given_unique_id(unique_id=item["unique_id"])
        action = replace_fields(action_to_change=action, mock_action=mock_action, context=self.context)  
        return action

    def validate_action(self, action, index):
        """Checks that a given action is still valid."""

        for field in ["actor", "target", "change"]:
            if not getattr(action, field):
                logging.debug(f"Action {action} is invalid - field {field} cannot be None")
                return False

        is_valid = action.change.validate(actor=action.actor, target=action.target)
        if is_valid:
            logging.debug(f"Action {action} is valid")
        else:
            logging.debug(f"Action {action} is invalid due to: {action.change.validation_error.message}")
        return is_valid

    def check_action_permission(self, action, index):

        logging.debug(f"Checking permission for action {action}")

        action.is_draft = False   # Remove from draft state

        if self.template_data.system:
            logging.debug("Approved as system action")
            return "approved"
        
        from concord.actions.permissions import has_permission
        action = has_permission(action=action)
        action.status = action.resolution.generate_status()
        logging.debug(f"Action {action} has status {action.status}")

        if action.status == "approved":
            return "approved"

        if action.status == "waiting":

            condition_items = []
            for source_id in action.resolution.conditions:
                self.context.add_condition_data(action.unique_id, source_id)
                condition_items.append(self.context.get_condition(action.unique_id, source_id))

            for item in condition_items:
                if item is None or item.status == "waiting":
                    return "waiting"
                elif item.status == "approved":
                    return "approved"

        return "rejected"
            
    def process_actions(self):
        """The heart of ActionContainer functionality - runs through action data, attempting to create
        actions and, if necessary, managing their conditions.  Typically called by commit_actions and 
        returns ok_to_commit indicating whether the commit needs to be rolled back or not."""

        from concord.actions.permissions import has_permission
        ok_to_commit = True
        actions = []   # not saved to DB, store of actions

        for index, item in enumerate(self.context.actions_and_results):

            logging.debug(f"Processing item {item}")
            action = self.get_db_action(item)
            actions.append(action)

            # Check if still valid
            if not self.validate_action(action, index):
                ok_to_commit = False
                continue

            # Check if has permission
            status = self.check_action_permission(action, index)
            logging.debug(f"Action {action} has permission {status}")
            ok_to_commit = False if status != "approved" else ok_to_commit
            if status == "rejected":  # if status is rejected, skip implementing
                continue

            # Implement action 
            result = action.implement_action()
            self.context.add_result(unique_id=item["unique_id"], result=result)  # add to context
            if status == "waiting":  # roll back status change that comes with implement_action()
                action.status = "waiting"

            action.save()  # save changes to action in DB

        return actions, ok_to_commit

    def determine_overall_status(self, actions):
        """Given actions generated by a run of process_actions, determines what the status of the
        whole container should be.
        
        'drafted' - used when first created
        'invalid' - if any of the actions created are invalid - shouldn't happen, but just in case
        'rejected' - used if any of the actions within the container are unconditionally rejected
        'waiting' - used if any of the actions within the container are 'waiting' or if any are missing
        'approved' - used if all actions within the container are approved
        'implemented' - used if all actions within container are implemented
        """

        if self.status == "implemented": 
            return "implemented"

        if any([action.status == "rejected" for action in actions]):
            return "rejected"
        if any([action.status == "waiting" for action in actions]): 
            return "waiting"
        if any([action.status == "invalid" for action in actions]):
            return "invalid"

        return "approved"

    def commit_actions(self, test=False, generate_conditions=True):  

        if self.status == "implemented":
            logging.warn(f"Attempted to commit actions of implemented container {self.pk}")
            return "implemented"

        try:
            with transaction.atomic():
                actions, ok_to_commit = self.process_actions()
                self.status = self.determine_overall_status(actions)
                if not ok_to_commit or test:
                    logging.info(f"Container {self.pk} not ok to commit, reverting (test = {test})")
                    raise DatabaseError()
                self.status = "implemented"            
        except DatabaseError as db_error:
            if generate_conditions:
                self.context.generate_conditions()

        if self.status is not "implemented":
            logging.debug(f"Reseting actions and results in context data, was {self.context.actions_and_results}")
            self.context.refresh_from_db()

        self.save()

        logging.debug(f"Saved container {self.pk} with overall status {self.status}")
        return self.status

    def get_action_data(self):
        """Gets a list of dicts with action, result and condition data for each action."""

        actions = []

        if self.status == "implemented":
            for action_dict in self.context.actions_and_results:
                action, result = self.context.get_action_and_result_data_from_cache(action_dict)
                conditions = self.context.get_condition_dicts_for_action(action_dict["unique_id"])
                actions.append({"action": action, "result": result, "conditions": conditions, "mock_action": None})
                logging.debug(f"Getting implemented actions: {actions}")
        else:
            for mock_action in self.template_data.action_list:
                conditions = self.context.get_condition_dicts_for_action(str(mock_action.unique_id))
                actions.append({"action": None, "mock_action": mock_action, "result": None, "conditions": conditions})
                logging.debug(f"Getting un-implemented actions: {actions}")
  
        return actions

    def get_actions(self):
        """Gets actions in db associated with container, as saved in self.context."""
        return [item["action"] for item in self.context.actions_and_results]


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

    is_permissioned_model = True

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


class TemplateModel(PermissionedModel):
    """The template model allows users to apply sets of actions to their communities."""

    template_data = TemplateField(default=Template, system=False)
    scopes = models.CharField(max_length=200)
    name = models.CharField(max_length=90, unique=True)
    user_description = models.CharField(max_length=500)
    supplied_fields = models.CharField(max_length=500)

    def __str__(self):
        return self.name

    def get_scopes(self):
        if self.scopes:
            return json.loads(self.scopes)
        return []
        
    def set_scopes(self, scopes):
        # TODO: possible set a list of allowable scopes and check here for them?
        if type(scopes) != list:
            raise TypeError(f"Scopes must be type list/array, not type {type(scopes)}")
        self.scopes = json.dumps(scopes)

    def get_supplied_fields(self):
        return json.loads(self.supplied_fields)

    def get_supplied_form_fields(self):
        """Loads template supplied fields and gets their forms, using field_helper.  Supplied
        fields typically have format like: 
        
            "field_x": ["RoleListField", None]
            "field_y": ["IntegerField", { "maximum": 2 }]
        """

        from concord.actions.field_utils import field_helper

        form_fields = []
        
        for field_name, field_info in self.get_supplied_fields().items():

            overrides = { "field_name": field_name }
            if field_info[1] is not None:
                overrides.update(field_info[1])

            form_field = field_helper(field_info[0], overrides)
            form_fields.append(form_field)

        return form_fields
        


