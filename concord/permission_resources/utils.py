"""Permission Resource utilities."""

import json
from collections import OrderedDict

from concord.actions.serializers import deserialize_state_change


def get_settable_permissions(*, target):
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


def check_configuration(action, permission):
    """Given a permission, check whether the action matches the configuration."""

    # Does permission.configuration contain keys?  If not, the permission is not
    # configured, so the action passes.
    if not json.loads(permission.configuration):
        return True

    # If configuration exists, instantiate the action's change type with its
    # change data.
    change_object = deserialize_state_change({
        "change_type": action.change.get_change_type(), "change_data":  action.change.get_change_data()})

    # Then call check_configuration on the state_change, passing in the permission
    # configuration data, and return the result.
    result, message = change_object.check_configuration(action, permission)
    if result is False and message:
        action.resolution.add_to_log(message)
    return result
