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
