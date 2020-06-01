from django.db import models

from concord.actions.serializers import (serialize_state_change, serialize_resolution, serialize_template,
    deserialize_state_change, deserialize_resolution, deserialize_template)


#################################
### Resolution Object & Field ###
#################################


class Resolution:
    '''The Resolution object is given the action's status and, optionally,
    how the action was resolved (if it was resolved), what role was used
    (if a role was used), the condition (if a condition was used) and whether
    or not the action in question is provisional.

    On instantiation, we infer values for is_resolved, is_approved, and
    passed_as.'''

    def __init__(self, *, status, resolved_through=None, role=None, 
        condition=None, provisional=False, log=None):

        # Store parameters
        self.status = status
        self.resolved_through = resolved_through
        self.role = role
        self.condition = condition
        self.provisional = provisional
        self.log = log

        self.is_resolved, self.is_approved, self.passed_as = None, None, None  # Initialize
        self.infer_values()

    def infer_values(self):
        self.check_if_resolved()
        self.check_if_approved()
        self.check_resolved_through()
        self.check_passed_as()

    def check_if_resolved(self):
        self.is_resolved = True if self.status in ["approved", "rejected", "implemented"] else False

    def check_if_approved(self):
        if self.is_resolved:
            self.is_approved = True if self.status in ["approved", "implemented"] else False

    def check_resolved_through(self):
        if self.is_resolved and self.is_approved:
            if self.resolved_through not in ["foundational", "governing", "specific", "system"]:
                raise ValueError("resolved_through was ", self.resolved_through, "; must be 'foundational', 'governing', or 'specific'")

    def check_passed_as(self):
        if self.is_resolved and self.is_approved:
            self.passed_as = "role" if self.role else "individual"
            self.role = self.role if self.role else None

    def __str__(self):
        detailed_passed_as = self.role if self.role else self.passed_as
        return "Action status %s (resolved through %s; passed as %s; condition %s; provisional %s)" % (self.status, 
            self.resolved_through, detailed_passed_as, self.condition, self.provisional)

    def approve_action(self, resolved_through, log=None, condition=None, role=None):
        if log:
            self.add_to_log(log)
        self.status = "approved"
        self.resolved_through = resolved_through
        self.condition = condition
        self.role = role
        self.infer_values()

    def reject_action(self, resolved_through=None, log=None, condition=None, role=None):
        if log:
            self.add_to_log(log)
        self.status = "rejected"
        self.resolved_through = resolved_through
        self.condition = condition
        self.role = role
        self.infer_values()

    def add_to_log(self, message):
        # "LOG: " is here to separate messages but we can probably do this better.
        if not self.log:
            self.log = message
        else:
            self.log += "  " + message


class ResolutionField(models.Field):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return Resolution(status="draft")
        return deserialize_resolution(value)

    def to_python(self, value):
        if isinstance(value, Resolution):
            return value
        if value is None:
            return Resolution(status="draft")
        return deserialize_resolution(value)

    def get_prep_value(self, value):
        if value is None:
            value = Resolution(status=draft)
        return serialize_resolution(value)


#############################
### Change Object & Field ###
#############################


class StateChangeField(models.Field):

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
        if issubclass(change_class, BaseStateChange):   # BUG: where is change_class coming from????
            return value
        return deserialize_state_change(value)

    def get_prep_value(self, value):

        # If actually given a state change, prep:
        from concord.actions.state_changes import BaseStateChange
        if issubclass(value.__class__, BaseStateChange):
            return serialize_state_change(value)

        # If already prepped for some reason, return as is:
        if type(value) == dict and "change_type" in value.keys() and "change_data" in value.keys():
            return value


###############################
### Template Object & Field ###
###############################


class Template(object):
    """Python object associated with the TemplateField CustomField. Contains action data which can be used
    to create an ActionContainer which will generate a set of related, configured objects."""

    def __init__(self, action_list=None, system=False):
        self.system = system
        self.action_list = action_list if action_list else []

    def has_template(self):
        return True if len(self.action_list) > 0 else False
        
    # Container manipulation methods

    def generate_action_container(self, trigger_action=None):
        from concord.actions.models import ActionContainer
        container = ActionContainer.objects.create()
        container.initialize(action_list=self.action_list, trigger_action=trigger_action, system=self.system)
        return container

    def generate_action_container_if_permitted(self, trigger_action=None):
        has_permission = self.check_permissions()
        if has_permission:
            container = self.generate_action_container(trigger_action)
            return True, container
        return False, None

    def generate_and_run_action_container_if_permitted(self, trigger_action=None):
        """Attempts to generate a container from the template, if permitted, and run said actions.
        Returns three values - a boolean indicating if a container was created, the container itself (if created),
        and the result of the run, if run."""
        container_created, container = self.generate_action_container_if_permitted(trigger_action)
        if container_created:
            result = container.commit_actions(test=False)
            return True, container, result
        return False, None, None

    def check_permissions(self):
        """
        Ideally, there'd be a method to check whether a user can run all the actions without, you know, actually
        doing it.  But given the existence of conditions, and even more dependent fields, I'm not sure how to check
        here. Maybe just check for "not straight reject"?  Like, no_auto_reject?  Probably need to wrap in an
        atomic commit as well if using ActionContainer.      
        """
        # FIXME: need to figure out how to implement this
        return True

    # Simple edit methods

    def add_action(self, action, position=None):
        if position:
            if position > len(self.action_list) - 1:
                raise IndexError(f"Position {position} given when action list is length { len(self.action_list) }")
            self.action_list.insert(action, position)
        else:
            self.action_list.append(action)

    def delete_action(self, action=None, position=None, last=False):
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

    # Description methods

    def automated_description(self):
        ...


class TemplateField(models.Field):

    def __init__(self, system=False, *args, **kwargs):
        self.system = system
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # only include kwargs if it's not the default
        if self.system:
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

        if type(value) == list and all([item.__class__ == MockAction for item in value]):
            return Template(action_list=value, system=self.system)

        return deserialize_template(value)

    def get_prep_value(self, value):

        if issubclass(value.__class__, Template):
            if self.system and not value.system:
                # This is a system field (likely a condition) that for some reason got initialized without this setting
                value.system = True
            return serialize_template(value)

        if type(value) == list and all([item.__class__ == MockAction for item in value]):
            return serialize_template(Template(action_list=value, system=self.system))

        # If already prepped for some reason, return as is???