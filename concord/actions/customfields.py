import json

from django.db import models


#################################
### Resolution Object & Field ###
#################################


class Resolution:
    '''The Resolution object is given the action's status and, optionally, how the action was resolved (if it 
    was resolved), what role was used (if a role was used), condition type and pk (if a condition was used) and 
    a log. On instantiation, we infer values for whether it's resolved (is_resolved) or approved (is_approved).'''

    def __init__(self, *, status, resolved_through=None, role=None, condition_list=None log=None):

        self.status = status
        self.resolved_through = resolved_through
        self.role = role
        self.log = log
        self.condition_list = condition_list if condition_list else []
        self.condition_pk = condition_pk
        self.condition_type = condition_type
        self.infer_values()

    def infer_values(self):
        self.check_if_resolved()
        self.check_if_approved()
        self.check_resolved_through()

    def check_if_resolved(self):
        self.is_resolved = True if self.status in ["approved", "rejected", "implemented"] else False

    def check_if_approved(self):
        if self.is_resolved:
            self.is_approved = True if self.status in ["approved", "implemented"] else False
        else:
            self.is_approved = None

    def check_resolved_through(self):
        if self.is_resolved and self.is_approved:
            if self.resolved_through not in ["foundational", "governing", "specific"]:
                raise ValueError("resolved_through was ", resolved_through, "; must be 'foundational', 'governing', or 'specific'")

    def __str__(self):
        pass_as_description = self.role if self.role else "individual"
        conditions = "; ".join(f"{condition['type']} - {condition['pk']}" for condition in self.condition_list)
        return f"Action status {self.status}: resolved through {self.resolved_through}; 
            passed as {pass_as_description}; conditions: {conditions}""
        
    def approve_action(self, resolved_through=None, log=None, condition_list=None, role=None):
        if log:
            self.add_to_log(log)
        self.status = "approved"
        self.resolved_through = resolved_through if resolved_through else self.resolved_through
        if not self.resolved_through:
            raise AttributeError("Approved actions must have 'resolved_through' set.")
        self.role = role
        self.condition_list = condition_list if condition_list else self.condition_list
        self.infer_values()

    def reject_action(self, resolved_through=None, log=None, condition_list=None, role=None):
        if log:
            self.add_to_log(log)
        self.status = "rejected"
        self.resolved_through = resolved_through
        self.role = role
        self.condition_list = condition_list if condition_list else self.condition_list
        self.infer_values()

    def add_to_log(self, message):
        # "LOG: " is here to separate messages but we can probably do this better.
        if not self.log:
            self.log = message
        else:
            self.log += "  " + message


def parse_resolution(resolution_string):
    resolution_dict = json.loads(resolution_string)
    return Resolution(status=resolution_dict['status'], resolved_through=resolution_dict['resolved_through'], 
        role=resolution_dict['role'], condition_list=resolution_dict['condition_list'], log=resolution_dict['log'])


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
        return parse_resolution(value)

    def to_python(self, value):
        if isinstance(value, Resolution):
            return value
        if value is None:
            return Resolution(status="draft")
        return parse_resolution(value)

    def get_prep_value(self, value):
        # if value == "draft_%_None_%_None_%_None_%_None":   REPLACE with new json version of draft
        #     return value
        if value is None:
            value = Resolution(status=draft)
        return json.dumps({
            "status": value.status,
            "resolved_through": value.resolved_through,
            "role": value.role,
            "condition_list": value.condition_list,
            "log": value.log
        })


#############################
### Change Object & Field ###
#############################


def create_change_object(change_type, change_data):
    """
    Finds change object using change_type and instantiates with change_data.
    """
    from django.utils.module_loading import import_string
    changeClass = import_string(change_type)
    if type(change_data) != dict:
        change_data = json.loads(change_data)
    return changeClass(**change_data)


def parse_state_change(state_change_string):
    state_change_dict = json.loads(state_change_string)
    return create_change_object(state_change_dict["change_type"], state_change_dict["change_data"])


class StateChangeField(models.Field):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        return parse_state_change(value)

    def to_python(self, value):

        from action.state_changes import BaseStateChange
        if issubclass(change_class, BaseStateChange):
            return value

        return parse_state_change(value)

    def get_prep_value(self, value):

        # If actually given a state change, prep:
        from concord.actions.state_changes import BaseStateChange
        if issubclass(value.__class__, BaseStateChange):
            return json.dumps({
                "change_type": value.get_change_type(),
                "change_data": value.get_change_data() })

        # If already prepped for some reason, return as is:
        if type(value) == dict and "change_type" in value.keys() and "change_data" in value.keys():
            return value