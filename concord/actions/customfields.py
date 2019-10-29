import json

from django.db import models


#################################
### Resolution Object & Field ###
#################################


class Resolution:
    '''The Resolution object is given the action's status and, optionally,
    how the action was resolved (if it was resolved), what role was used
    (if a role was used), and the condition (if a condition was used).

    On instantiation, we infer values for is_resolved, is_approved, and
    passed_as.'''

    def __init__(self, *, status, resolved_through=None, role=None, 
        condition=None):

        # Initialize attributes
        self.is_resolved = None
        self.is_approved = None
        self.resolved_through = None
        self.passed_as = None
        self.role = None

        self.condition = condition

        if status in ["approved", "rejected", "implemented"]:
            self.status = status
            self.is_resolved = True
        elif status in ["sent", "draft"]:
            self.status = status
            self.is_resolved = False
        else: 
            raise ValueError("Status passed to Resolution object must be ",
                " approved, rejected, implemented or sent, was: ", status)

        if self.is_resolved:

            self.is_approved = True if self.status in ["approved", "implemented"] else False
        
            if self.is_approved:

                if resolved_through in ["foundational", "governing", "specific"]:
                    self.resolved_through = resolved_through
                else:
                    raise ValueError("resolved_through was ", resolved_through, 
                        "; must be 'foundational', 'governing', or 'specific'")

                if role:
                    self.passed_as = "role"
                    self.role = role
                else:
                    self.passed_as = "individual"
                    self.role = None

    def __str__(self):
        # FIXME: should a __str__ be this complicated?

        condition = self.condition if self.condition else "no conditions"

        if not self.is_resolved:
            return "Action is unresolved with %s" % (condition)

        if not self.is_approved:
            return "Action is rejected through %s with %s" % (self.resolved_through,
                condition)

        if self.passed_as == "individual":
            return "Action is accepted, passing as individual, with %s" % (condition)
        elif self.passed_as == "role":
            return "Action is accepted, passing as role %s, with %s" % (self.role, 
                condition)
        else: 
            return "Action is accepted, unknown if passed as role or indiv, with %s" % (condition)


def parse_resolution(resolution_string):
    status, resolved_through, role, condition = resolution_string.split("_%_")
    return Resolution(status=status, resolved_through=resolved_through, 
        role=role, condition=condition)


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
        if value == "draft_%_None_%_None_%_None":
            return value
        if value is None:
            return "draft_%_None_%_None_%_None"
        return "_%_".join([str(value.status), str(value.resolved_through), 
            str(value.role), str(value.condition)])


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