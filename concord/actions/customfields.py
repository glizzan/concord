import json

from django.db import models


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
            if self.resolved_through not in ["foundational", "governing", "specific"]:
                raise ValueError("resolved_through was ", resolved_through, "; must be 'foundational', 'governing', or 'specific'")

    def check_passed_as(self):
        if self.is_resolved and self.is_approved:
            self.passed_as = "role" if self.role else "individual"
            self.role = self.role if self.role else None

    def __str__(self):
        detailed_passed_as = self.role if self.role else self.passed_as
        return "Action status %s (resolved through %s; passed as %s; condition %s; provisional %s)" % (self.status, 
            self.resolved_through, detailed_passed_as, self.condition, self.provisional)

    def approve_action(self, resolved_through, log=None, condition=None, role=None):
        self.log = log if log else ""   # FIXME: append instead?
        self.status = "approved"
        self.resolved_through = resolved_through
        self.condition = condition
        self.role = role
        self.infer_values()

    def reject_action(self, resolved_through=None, log=None, condition=None, role=None):
        self.log = log if log else ""    # FIXME: append instead?
        self.status = "rejected"
        self.resolved_through = resolved_through
        self.condition = condition
        self.role = role
        self.infer_values()


def parse_resolution(resolution_string):
    resolution_dict = json.loads(resolution_string)
    return Resolution(status=resolution_dict['status'], resolved_through=resolution_dict['resolved_through'], 
        role=resolution_dict['role'], condition=resolution_dict['condition'], 
        provisional=resolution_dict['provisional'], log=resolution_dict['log'])


class ResolutionField(models.Field):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'resolution'  

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
            "condition": value.condition,
            "provisional": value.provisional,
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
        return 'statechange'  

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