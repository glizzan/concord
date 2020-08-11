import inspect, json
from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType


def get_settable_permissions(* , target):
    """Gets a list of all permissions that may be set on the model."""

    settable_permissions = target.get_settable_state_changes()

    if hasattr(target, 'pk'):
        bases = target.__class__.__bases__
    else:
        bases = target.__bases__
    
    for parent in bases:
        if hasattr(parent, "get_settable_state_changes"):
            settable_permissions += parent.get_settable_state_changes()

    # Remove duplicates while preserving order
    return list(OrderedDict.fromkeys(settable_permissions))


def format_as_tuples(permissions):
    formatted_permissions = []
    for permission in permissions:
        formatted_permissions.append((permission.get_change_type(), 
            permission.description))
    return formatted_permissions

def format_as_list_of_strings(permissions):
    formatted_permissions = []
    for permission in permissions:
        formatted_permissions.append(permission.get_change_type())
    return formatted_permissions


# Checks inputs of actors, roles, etc.
# NOTE: should be able to delete this once custom fields are implemented (can we do so now?)
def check_permission_inputs(dict_of_inputs):
    """
    Decorator to help with type issues, example usage: 
    @check_permission_inputs(dict_of_inputs={'role_pair': 'role_pair', 'community': 'string_pk'})
    """
    def check_permission_inputs_decorator(func):
        def function_wrapper(*args, **kwargs):
            if type(dict_of_inputs) is not dict:
                raise TypeError("check_permission_inputs must be passed a dict.")
            for key, value in kwargs.items():
                input_type = dict_of_inputs[key]
                if input_type == "role_pair":
                    community, role = value.split("_")
                    int(community)
                    continue
                if input_type == "json":
                    json.loads(value)
                    continue
                if input_type == "string_pk":
                    int(value)
                    if type(value) == int:
                        raise TypeError("String_pk should be string, not int")
                    continue
                if input_type == "simple_string":
                    if "[" in value or "{" in value:
                        raise TypeError("Simple string cannot include [ or {")
                    continue
                raise ValueError("Check_permission_inputs was given unknown input_type")

            return func(*args, **kwargs)
        return function_wrapper
    return check_permission_inputs_decorator


def check_configuration(action, permission):

    # Does permission.configuration contain keys?  If not, the permission is not
    # configured, so the action passes.
    if not json.loads(permission.configuration):
        return True

    # If configuration exists, instantiate the action's change type with its
    # change data.  
    from concord.actions.serializers import deserialize_state_change
    change_object = deserialize_state_change({"change_type": action.change.get_change_type(), 
        "change_data":  action.change.get_change_data()})

    # Then call check_configuration on the state_change, passing in the permission
    # configuration data, and return the result.
    result, message = change_object.check_configuration(action, permission)
    if result == False and message:
        action.resolution.add_to_log(message)
    return result


def get_verb_given_permission_type(permission):
    from concord.actions.utils import get_state_change_object
    state_change_object = get_state_change_object(permission)
    return state_change_object.description.lower()
