"""Permission Resource utilities."""

import json, logging
from collections import OrderedDict

from concord.actions.serializers import deserialize_state_change
from concord.actions.utils import get_default_permissions


logger = logging.getLogger(__name__)


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
        "change_type": action.change.get_change_type(), "change_data": action.change.get_change_data()})

    # Then call check_configuration on the state_change, passing in the permission
    # configuration data, and return the result.
    result, message = change_object.check_configuration(action, permission)

    if result is False and message:
        action.resolution.add_to_log(message)
    return result


def delete_permissions_on_target(target):
    """Given a target PermissionedModel object, find all permissions set on it and delete them."""

    from concord.actions.utils import Client
    client = Client(target=target)

    permissions = client.PermissionResource.get_permissions_on_object(target_object=target)

    for permission in permissions:
        delete_permissions_on_target(permission)
        logging.info(f"Deleting {permission}")
        permission.delete()


def set_default_permissions(actor, instance):
    """Given an actor, target, and model, set the default permissions associated with that model."""

    from concord.actions.utils import Client
    client = Client(actor=actor, target=instance)

    if hasattr(instance, "is_community") and instance.is_community:
        model_type = "community"
    else:
        model_type = instance.__class__.__name__.lower()

    default_permissions = get_default_permissions()

    for permission in default_permissions.get(model_type, []):
        logger.debug(f"Adding permission with parameters {permission} to {instance}")
        condition_data = permission.pop("condition", None)
        action, permission = client.PermissionResource.add_permission(**permission)
        if condition_data:
            client.update_target_on_all(target=permission)
            client.Conditional.add_condition(**condition_data)
