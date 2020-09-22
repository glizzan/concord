"""This module contains custom fields used by this package's models.py, as well as the Python objects used to
create those custom fields, which are occasionally used on their own."""

import logging

from django.db import models, transaction
from concord.actions.utils import MockAction, replace_fields
from concord.actions.text_utils import (action_status_to_text, mock_action_to_text, foundational_actions_to_text,
                                        supplied_fields_to_text)

from concord.actions.serializers import (serialize_state_change, serialize_resolution, serialize_template,
                                         deserialize_state_change, deserialize_resolution, deserialize_template)


logger = logging.getLogger(__name__)


#################################
### Resolution Object & Field ###
#################################


class Resolution:
    """The Resolution object stores information about the Action's status as well as its passage
    through the permissions pipeline.

    The meta_status attribute tracks what 'stage' of the process the Action is in - created, proposed,
    taken, waiting, or resolved.  'Taken' and 'waiting' statuses can be passed through the permissions
    pipeline, while 'created' and 'proposed' are not yet passed through the permissions pipeline, and
    'resolved' cannot be passed through the pipeline again.

    We also store the most recent runs through the pipeline in the three pipeline statuses:
    'foundational_status', 'governing_status', and 'specific_status'.  Pipeline statuses and meta statuses
    are used by generate_status to determine the overall status of the action, which is referenced from
    the action itself via its status property.

    Finally, westore a log, as well as information about how an action was approved (if it was approved) and
    information about the template involved (if the action is applying a template)."""

    def __init__(self, *, meta_status="created", foundational_status="not tested", specific_status="not tested",
                 governing_status="not tested", conditions=None, log=None, approved_through=None,
                 approved_role=None, approved_condition=None, template_info=None):

        self.meta_status = meta_status
        self.foundational_status = foundational_status
        self.specific_status = specific_status
        self.governing_status = governing_status
        self.conditions = conditions if conditions else {}
        self.log = log if log else ""
        self.approved_through = approved_through
        self.approved_role = approved_role
        self.approved_condition = approved_condition
        self.template_info = template_info

    def __str__(self):
        return f"Action status {self.generate_status()} - {self.get_status_string()}"

    def __repr__(self):
        return f"""Action Resolution(meta_status={self.meta_status}, foundational_status={self.foundational_status},
                specific_status={self.specific_status}, governing_status={self.governing_status},
                conditions={self.conditions}, log={self.log}, approved_through={self.approved_through},
                approved_role={self.approved_role}, approved_condition={self.approved_condition})"""

    @property
    def is_resolved(self):
        """Property method returning True if the generated status is a 'final' status, False if otherwise."""
        return True if self.generate_status() in ["approved", "rejected", "implemented"] else False

    @property
    def is_approved(self):
        """Property method returning True if the generated status is 'approved' or 'implemented'."""
        return True if self.generate_status() in ["approved", "implemented"] else False

    @property
    def passed_as(self):
        """Property method returning whether the action was approved via a role or individual, if it was approved.
        Otherwise returns None."""
        if self.is_approved:
            return "role" if self.approved_role else "individual"
        return None

    def refresh_pipeline_status(self):
        """When re-running an action, we need to refresh the pipeline-specific statuses."""
        self.foundational_status, self.governing_status, self.specific_status = "not tested", "not tested", "not tested"

    def generate_pipeline_status(self):
        """Determines an overall status given the three sub-statuses."""

        # Action only needs to be approved by one pipeline to be approved
        if "approved" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "approved"

        # If any pipeline is waiting, status is waiting
        if "waiting" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "waiting"

        # If any of the pipeline is rejected, status is rejected
        if "rejected" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "rejected"

        # we haven't actually run the pipeline yet, so return none

    def generate_status(self):
        """Gets overall status"""

        if self.meta_status in ["created", "proposed", "implemented"]:
            return self.meta_status

        pipeline_status = self.generate_pipeline_status()
        if pipeline_status:
            return pipeline_status

        return self.meta_status  # will be 'taken' or 'waiting'

    def get_status_string(self):
        """Helper method which returns a 'plain English' description of the action status."""
        return action_status_to_text(self)

    def approve_action(self, pipeline, approved_role=None, approved_condition=None):
        """Sets the status for the calling pipeline to approved, which will set overall status to approved."""
        setattr(self, pipeline + "_status", "approved")
        self.approved_through = pipeline
        self.approved_role = approved_role
        self.approved_condition = approved_condition
        log_string = f"action approved through {self.approved_through} with role {approved_role} and " + \
                     f"condition {approved_condition}"
        self.add_to_log(log_string)
        logging.debug(log_string)

    def reject_action(self, pipeline, log=None):
        """Sets the status for the calling pipeline to rejected."""
        setattr(self, pipeline + "_status", "rejected")
        if log:
            self.add_to_log(log)
        logging.debug(f"Rejecting action in pipeline {pipeline} - log: {log}")

    def set_waiting(self, pipeline, log=None):
        """Sets the status for the calling pipeline to waiting."""
        setattr(self, pipeline + "_status", "waiting")
        if log:
            self.add_to_log(log)

    def add_to_log(self, message):
        """Appends messsage to log field.  If log goes past 300 characters, we assume the log is just checking
        a waiting condition over and over, and don't save."""
        if len(self.log) < 300:
            self.log = self.log + "  " + message if self.log else message

    def condition_created(self, source_id):
        """Marks a source_id as having a condition created for it."""
        self.conditions[source_id] = True

    def uncreated_conditions(self):
        """Returns a list of source_ids corresponding to uncreated conditions."""
        return [source_id for source_id, is_created in self.conditions.items() if not is_created]

    def apply_condition_data(self, pipeline, permission, matched_role, condition_data):
        """Updates resolution based on condition data."""

        if condition_data["condition_item"]:
            condition_name = condition_data["condition_item"].get_model_name()
        else:
            condition_name = "not created"

        check_string = f"permission {permission}" if permission else f"{pipeline} authority"

        if condition_data["condition_status"] == "waiting":
            log = f"waiting on condition '{condition_name}' for {check_string} (role {matched_role})"
            self.set_waiting(pipeline=pipeline, log=log)
        elif condition_data["condition_status"] == "not created":
            log = f"{pipeline}: waiting on uncreated condition for {check_string} (role {matched_role})"
            self.set_waiting(pipeline=pipeline, log=log)
            self.conditions.update({condition_data["source_id"]: False})   # False since condition is not created
        elif condition_data["condition_status"] == "approved":
            self.approve_action(pipeline=pipeline, approved_role=matched_role, approved_condition=condition_name)

        return condition_name

    def process_resolution(self, pipeline, permission, passes, matched_role, condition_data):
        """Parses the result of a permissions or conditions check and updates resolution accordingly."""

        if condition_data:
            condition_name = self.apply_condition_data(pipeline, permission, matched_role, condition_data)

        if not condition_data and passes:
            self.approve_action(pipeline=pipeline, approved_role=matched_role)

        # If pipeline is specific, don't reject the action - we have more specific permissions to check
        if pipeline == "specific":
            return

        if condition_data["condition_status"] == "rejected":
            # should be true - we don't call here in foundational or governing unless we're checking conditions
            log = f"action passed {pipeline} pipeline but was rejected by condition {condition_name}"
            self.reject_action(pipeline=pipeline, log=log)


class ResolutionField(models.Field):
    """Django model field definition for Resolution object."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return Resolution()
        return deserialize_resolution(value)

    def to_python(self, value):
        if isinstance(value, Resolution):
            return value
        if value is None:
            return Resolution()
        return deserialize_resolution(value)

    def get_prep_value(self, value):
        if value is None:
            value = Resolution()
        return serialize_resolution(value)


#############################
### Change Object & Field ###
#############################


class StateChangeField(models.Field):
    """Django model field definition for State Change object."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        return deserialize_state_change(value)

    def to_python(self, value):
        from action.state_changes import BaseStateChange
        if issubclass(value, BaseStateChange):   # BUG: where is change_class coming from????
            return value
        return deserialize_state_change(value)

    def get_prep_value(self, value):

        # If actually given a state change, prep:
        from concord.actions.state_changes import BaseStateChange
        if issubclass(value.__class__, BaseStateChange):
            return serialize_state_change(value)

        # If already prepped for some reason, return as is:
        if isinstance(value, dict) and "change_type" in value.keys() and "change_data" in value.keys():
            return value


###############################
### Template Object & Field ###
###############################


class Template(object):
    """Python object associated with the TemplateField CustomField. Contains action data which can be used
    to create an ActionContainer which will generate a set of related, configured objects.

    Args:
        action_list: list of Mock Actions
            A list of Mock Actions which will be taken on the target of the template.
        description: string
            A human-readable description of what the actions in the template accomplish.
        system: boolean
            Indicates whether the client is called without a user by the system. Used for condition templates
            and other templates made and used by the system.
    """

    def __init__(self, action_list=None, description=None, system=False):
        self.system = system
        self.action_list = action_list if action_list else []
        self.description = description if description else ""

    def __repr__(self):
        action_changes = ", ".join([str(action) for action in self.action_list])
        return f"Template(action_list={action_changes}, system={self.system})"

    def __str__(self):
        return self.__repr__()

    def has_template(self):
        """Returns True if there are mock actions in the Template model."""
        return True if len(self.action_list) > 0 else False

    def apply_template(self, actor, target, trigger_action, supplied_fields=None, rollback=False):
        """Applies template by creating the actions one by one and implementing them.  We track older actions
        and results in case they're needed by later actions."""

        from concord.actions.models import Action

        context_instances = trigger_action.change.all_context_instances(trigger_action)
        context = {"supplied_fields": supplied_fields, "context": context_instances, "actions_and_results": []}

        try:

            validation_errors = []

            with transaction.atomic():

                for mock_action in self.action_list:

                    # create action and replace fields
                    action_model = Action(actor=actor, change=mock_action.change, target=target)
                    action_model = replace_fields(action_to_change=action_model, mock_action=mock_action,
                                                  context=context)
                    action_model.save()

                    is_valid = action_model.change.validate(actor=action_model.actor, target=action_model.target)
                    if not is_valid:
                        validation_errors.append(action_model.change.validation_error)

                    # implement and save results to context
                    result = action_model.change.implement(actor=action_model.actor, target=action_model.target)
                    context["actions_and_results"].append({"action": action_model, "result": result})

                if rollback:
                    raise ValueError("Pro forma error to roll back transaction when validating")

        except ValueError as error:
            logger.debug(str(error))
            if hasattr(trigger_action, "refresh_from_db"):
                trigger_action.refresh_from_db()
            if hasattr(target, "refresh_from_db"):
                target.refresh_from_db()

        if validation_errors:
            return {"errors": validation_errors}

        return context["actions_and_results"]

    def programmatic_description_uninstantiated(self, name, supplied_field_options=None):
        """Gets a complete, programmatically generated list of actions.  No trigger action, as this is called
        when the template has not yet been triggered.  Supplied fields is a list of fields to be supplied and
        contains no user-supplied values."""
        actions = [mock_action_to_text(mock) for mock in self.action_list]
        supplied_fields = supplied_fields_to_text(None, supplied_field_options)
        foundational = foundational_actions_to_text(self.action_list)
        return {"name": name, "actions": actions, "supplied_fields": supplied_fields, "foundational": foundational}

    def programmatic_description(self, name, trigger_action=None, supplied_field_data=None,
                                 supplied_field_options=None):
        """Gets a complete, programmatically generated list of actions.  Trigger action and supplied fields are
        technically optional but should be passed in as this is called when a template has actually been applied
        or is in the process of being applied."""
        actions = [mock_action_to_text(mock, trigger_action) for mock in self.action_list]
        supplied_fields = supplied_fields_to_text(supplied_field_data, supplied_field_options)
        foundational = foundational_actions_to_text(self.action_list)
        return {"name": name, "actions": actions, "supplied_fields": supplied_fields, "foundational": foundational}

    def get_mock_action_given_unique_id(self, unique_id):
        """Gets a Mock Action from the action list if it matches the unique_id passed in."""
        for mock_action in self.action_list:
            if mock_action.unique_id == unique_id:
                return mock_action

    # Simple edit methods

    def add_action(self, action, position=None):
        """Adds mock action to action_list. If a position is passed in, adds the action at that position, otherwise
        appends to the end of the list."""
        if position:
            if position > len(self.action_list) - 1:
                raise IndexError(f"Position {position} given when action list is length { len(self.action_list) }")
            self.action_list.insert(action, position)
        else:
            self.action_list.append(action)

    def delete_action(self, action=None, position=None, last=False):
        """"Deletes mock action from the list. If position is passed in, removes the action at that position. If
        last arg is set to True, removes the last action.  If action is passed in, removes the action."""
        if position:
            if position > len(self.action_list) - 1:
                raise IndexError(f"Position {position} given when action list is length { len(self.action_list) }")
            self.action_list.pop(position)
        elif last:
            self.action_list.pop(len(self.action_list) - 1)
        elif action:
            self.action_list.remove(action)
        if not action and not position and not last:
            raise ValueError("Must provide action or position or last = True to delete_action.")


class TemplateField(models.Field):
    """Django model field definition for Template object."""

    def __init__(self, system=False, *args, **kwargs):
        self.system = system
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.system:    # only include kwargs if it's not the default
            kwargs['system'] = self.system
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):

        if value is None:
            return Template(system=self.system)

        return deserialize_template(value)

    def to_python(self, value):

        if value is None:
            return Template(system=self.system)

        if issubclass(value.__class__, Template):
            return value

        if isinstance(value, list) and all([item.__class__ == MockAction for item in value]):
            return Template(action_list=value, system=self.system)

        return deserialize_template(value)

    def get_prep_value(self, value):

        if issubclass(value.__class__, Template):
            if self.system and not value.system:
                # This is a system field (likely a condition) that somehow got initialized without this setting
                value.system = True
            return serialize_template(value)

        if isinstance(value, list) and all([item.__class__ == MockAction for item in value]):
            return serialize_template(Template(action_list=value, system=self.system))
