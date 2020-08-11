"""
This module implements the logic of the permission system.

The `has_permission` function is called by external callers, while the rest of the functions are used by
has_permission.
"""

import logging

from concord.actions.utils import Client
from concord.permission_resources.utils import check_configuration


logger = logging.getLogger(__name__)


def check_conditional(action, community_or_permission, leadership_type=None):
    """Checks to see if a condition item has been created for the action.

    Args:
        action: Action Model
            The Action which is being passed through the permissions pipeline.
        community_or_permission: Model
            Either community model or permission model.
        leadership_type: str
            Either "owner" or "governor". Required if community_or_permission is community.
            ignored if community_or_permission is permission.

    Returns a dict containing condition information if condition_item exists or, if condition item
    does not exist, the same dict structure populated by Nones."""

    client = Client()
    source_id = f"{leadership_type}_{str(community_or_permission.pk)}" if leadership_type else \
                f"perm_{str(community_or_permission.pk)}"
    condition_item = client.Conditional.get_condition_item_given_action_and_source(action_pk=action.pk,
                                                                                  source_id=source_id)

    return {
        "condition_item": condition_item,
        "source_id": source_id,
        "condition_status": condition_item.condition_status() if condition_item else "not created"
    }


def foundational_permission_pipeline(action):
    """Handles logic for foundational actions.

    When an action is passed through the foundational pipeline, it is not passed through the governing or specific
    permission pipeline. So, if we don't have the authority, we reject the action."""
    
    client = Client()
    community = client.Community.get_owner(owned_object=action.target)
    client.Community.set_target(target=community)

    has_authority, matched_role = client.Community.has_foundational_authority(actor=action.actor)
    if not has_authority:
        action.resolution.reject_action(pipeline="foundational")
        return action

    if not community.has_owner_condition():
        action.resolution.approve_action(pipeline="foundational", approved_role=matched_role)
        return action

    condition_data = check_conditional(action, community, "owner")
    action.resolution.process_resolution("foundational", None, True, matched_role, condition_data)
    return action


def check_specific_permission(permission, action):
    """Helper method called by specific permissions pipeline.  Given a permission, checks to see if its active,
    if it has the right configuration, that the actor satisfies the permission, and whether the action has a
    condition that passes, in that order.

    Returns:
        True or False indicating whether permission passes
        Str or the role that the actor matched to, if it exists, or None
        Dict of the condition data from the condition set on the permission, or None
    """

    if not permission.is_active:
        return False, None, None

    if not check_configuration(action, permission):
        return False, None, None

    client = Client()
    client.PermissionResource.set_target(target=action.target)
    # permClient = PermissionResourceClient(actor="system", target=action.target)
    actor_satisfies, matched_role = client.PermissionResource.actor_satisfies_permission(actor=action.actor, permission=permission)
    if not actor_satisfies:
        return False, None, None

    if permission.has_condition():
        condition_data = check_conditional(action, permission)
        passes = True if condition_data["condition_status"] == "approved" else False
        return passes, matched_role, condition_data

    return True, matched_role, None


def specific_permission_pipeline(action):
    """Checks the target for specific permissions matching the change type and configuration of the action.

    If matching permissions are found, we check to see if the actor satisfies the permission. If the actor does
    satisfy, we look for conditions. If any permissions have no condition, the action is approved. If there are
    conditions, they are saved to the conditions list.

    If after this the action is not approved, we check to see whether the target is nested on another object which
    may have permissions set on it. For instance, the target may be a post in a forum, where the forum has an
    'edit post' permission that applies across all posts. We go through the same process for each of the nested
    permissions.

    At the end of all this, if any of these permissions pass, the action is approved. If any are waiting, the action
    is set to waiting. If none are approved or waiting, the action is rejected."""

    client = Client()
    client.PermissionResource.set_target(target=action.target)

    # Get and check target level permissions
    for permission in client.PermissionResource.get_specific_permissions(change_type=action.change.get_change_type()):
        passes, matched_role, condition_data = check_specific_permission(permission, action)
        action.resolution.process_resolution("specific", permission, passes, matched_role, condition_data)
        if passes:
            return action

    # If we're still here, that means nothing matched without a condition, so now we look for nested permissions
    for nested_object in action.target.get_nested_objects():
        client.PermissionResource.set_target(target=nested_object)
        for permission in client.PermissionResource.get_specific_permissions(change_type=action.change.get_change_type()):
            passes, matched_role, condition_data = check_specific_permission(permission, action)
            action.resolution.process_resolution("specific", permission, passes, matched_role, condition_data)
            if passes:
                return action

    # If after all of this, nothing passes and nothing's waiting, reject.
    if action.resolution.specific_status != "waiting":
        action.resolution.reject_action(pipeline="specific", log="Action did not pass any permissions.")
    return action


def governing_permission_pipeline(action):
    """Checks whether the actor behind the action has governing permissions and if so, passes."""

    client = Client()
    community = client.Community.get_owner(owned_object=action.target)
    client.Community.set_target(target=community)

    has_authority, matched_role = client.Community.has_governing_authority(actor=action.actor)
    if not has_authority:
        action.resolution.reject_action(pipeline="governing", log="user does not have governing permission")
        return action

    if not community.has_governor_condition():
        action.resolution.approve_action(pipeline="governing", approved_role=matched_role)
        return action

    condition_data = check_conditional(action, community, "governor")
    action.resolution.process_resolution("governing", None, True, matched_role, condition_data)
    return action


def has_permission(action):
    """has_permission directs the flow of logic in the permissions pipeline.  It returns information about
    whether the action has permsision to take the action and if there are any conditions that need to be
    triggered.  It does not change the database and it does not alter the action object other than updating
    its resolution field and, optionally, adding a conditions_list attribute with source_ids for uncreated
    conditions.

    If the foundational permission is enabled or the change type is a foundational change (like change_owner),
    we go into the foundational permission pipeline and no other pipeline.

    If the governing permission is enabled, we try that pipeline. If the action is approved by the governing
    pipeline and we finish with the permission pipeline, otherwise we move on to the last option, the specific
    permission pipeline.
    """

    # Check for criteria indicating we should use the foundational permission pipeline
    if action.change.is_foundational or action.target.foundational_permission_enabled:
        return foundational_permission_pipeline(action)

    # Check that object allows us to use governing permission, if yes, try governing pipeline
    if action.target.governing_permission_enabled:
        action = governing_permission_pipeline(action)

    # If action was approved by the governing pipeline, return it, otherwise try specific permission pipeline too
    if action.resolution.governing_status == "approved":
        return action
    return specific_permission_pipeline(action)
