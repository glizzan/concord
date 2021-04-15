"""Permission Resource utilities."""

import logging, copy
from collections import OrderedDict

from concord.utils.lookups import get_default_permissions


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


def delete_permissions_on_target(target):
    """Given a target PermissionedModel object, find all permissions set on it and delete them."""

    from concord.utils.helpers import Client
    client = Client(target=target)

    permissions = client.PermissionResource.get_permissions_on_object(target_object=target)

    for permission in permissions:
        delete_permissions_on_target(permission)
        logging.info(f"Deleting {permission}")
        permission.delete()


def set_default_permissions(actor, instance):
    """Given an actor, target, and model, set the default permissions associated with that model."""

    from concord.utils.helpers import Client
    client = Client(actor=actor)

    if hasattr(instance, "is_community") and instance.is_community:
        model_type = "community"
    else:
        model_type = instance.__class__.__name__.lower()

    default_permissions = get_default_permissions()

    for permission in default_permissions.get(model_type, []):

        logger.debug(f"Adding permission with parameters {permission} to {instance}")
        client.update_target_on_all(target=instance)

        if "conditions" in permission:
            permission_dict = copy.deepcopy(permission)
            conditions = permission_dict.pop("conditions", [])
            action, created_permission = client.PermissionResource.add_permission(**permission_dict)

            client.update_target_on_all(target=created_permission)
            for condition_data in conditions:
                action, result = client.Conditional.add_condition(**condition_data)
        else:
            action, created_permission = client.PermissionResource.add_permission(**permission)
