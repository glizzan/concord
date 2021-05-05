"""This module contains custom fields used by this package's models.py, as well as the Python objects used to
create those custom fields, which are occasionally used on their own."""

import logging, json

from django.db import models, transaction
from concord.actions.utils import MockAction
from concord.utils.dependent_fields import replace_fields
from concord.utils.text_utils import (mock_action_to_text, foundational_actions_to_text, supplied_fields_to_text)
from concord.utils.converters import ConcordConverterMixin


logger = logging.getLogger(__name__)


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
        return ConcordConverterMixin.deserialize(value)

    def to_python(self, value):
        from concord.actions.state_changes import BaseStateChange
        if issubclass(value, BaseStateChange):
            return value
        return ConcordConverterMixin.deserialize(value)

    def get_prep_value(self, value):

        # If actually given a state change, prep:
        from concord.actions.state_changes import BaseStateChange
        if issubclass(value.__class__, BaseStateChange):
            return value.serialize(to_json=True)

        # If already prepped for some reason, return as is:
        if isinstance(value, dict) and "class" in value and "StateChange" in value["class"]:
            return json.dumps(value)


###############################
### Template Object & Field ###
###############################


class Template(ConcordConverterMixin):
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
                    action_model = replace_fields(action=action_model, mock_action=mock_action, context=context)
                    action_model.save()

                    is_valid = action_model.change.validate(actor=action_model.actor, target=action_model.target)
                    if not is_valid:
                        validation_errors.append(action_model.change.validation_error)

                    # implement and save results to context
                    result = action_model.change.implement_action(actor=action_model.actor, target=action_model.target)
                    action_model.status = "implemented"
                    action_model.add_log({"approved_through": "part of template"})
                    action_model.save()
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

        return Template.deserialize(value)

    def to_python(self, value):

        if value is None:
            return Template(system=self.system)

        if issubclass(value.__class__, Template):
            return value

        if isinstance(value, list) and all([item.__class__ == MockAction for item in value]):
            return Template(action_list=value, system=self.system)

        return Template.deserialize(value)

    def get_prep_value(self, value):

        if issubclass(value.__class__, Template):
            if self.system and not value.system:
                # This is a system field (likely a condition) that somehow got initialized without this setting
                value.system = True
            return value.serialize(to_json=True)

        if isinstance(value, list) and all([item.__class__ == MockAction for item in value]):
            template = Template(action_list=value, system=self.system)
            return template.serialize(to_json=True)
