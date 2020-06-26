"""
This module contains the logic at the heart of the permissions system.  has_permission, at the bottom of the
file, is called by external callers, while the rest of the methods are used by has_permission.
"""

from collections import namedtuple

from django.contrib.auth.models import User

from concord.actions.state_changes import foundational_changes
from concord.conditionals.client import ConditionalClient
from concord.communities.client import CommunityClient
from concord.permission_resources.client import PermissionResourceClient
from concord.permission_resources.utils import check_configuration


def check_conditional(action, community_or_permission, leadership_type=None):
    """Given a community or permission with a condition template set on it, checks to see if a 
    condition item has been created for this action.  Generally called after we check that a condition
    is set on the community or permission, but won't fail if there's no condition set - will simply 
    return 'not created', and it's up to the caller not to get confused."""

    conditionalClient = ConditionalClient(system=True)

    source_id = leadership_type + "_" + str(community_or_permission.pk) if leadership_type else \
                "perm_" + str(community_or_permission.pk)
    
    if hasattr(action, "is_mock") and action.is_mock:   # TODO: refactor so we don't use mocks
        condition_item = None
    else:    
        condition_item = conditionalClient.get_condition_item_given_action_and_source(action_pk=action.pk, source_id=source_id)

    return {
        "condition_item": condition_item,
        "source_id": source_id,
        "condition_status": condition_item.condition_status() if condition_item else "not created"
    }


def apply_condition_data_to_action(action, condition_data, pipeline, role):
    """Helper method which updates the action's resolution field given condition data returned by 
    check_conditional."""
    
    if condition_data["condition_item"] is not None:
        condition_name = condition_data["condition_item"].get_model_name()

    if condition_data["condition_status"] == "approved":
        action.resolution.approve_action(pipeline=pipeline, approved_role=role, approved_condition=condition_name)
    elif condition_data["condition_status"] == "rejected": 
        log=f"action passed {pipeline} pipeline but was rejected by condition {condition_name}"
        action.resolution.reject_action(pipeline=pipeline, log=log)
    elif condition_data["condition_status"] == "waiting":
        log=f"action passed {pipeline} pipeline, now waiting on condition {condition_name}"
        action.resolution.set_waiting(pipeline=pipeline, log=log)
    elif condition_data["condition_status"] == "not created":
        action.resolution.set_waiting(pipeline=pipeline, log=f"action passed {pipeline} pipeline, now waiting on uncreated condition")
        action.resolution.conditions.append(condition_data["source_id"])

    return action


def foundational_permission_pipeline(action):
    """Handles logic for foundational actions. Note that because we know we *only* go through the foundational
    pipeline, if we don't have authority we reject before returning."""
   
    communityClient = CommunityClient(system=True) 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)

    has_authority, matched_role = communityClient.has_foundational_authority(actor=action.actor)
    if not has_authority:
        action.resolution.reject_action(pipeline="foundational")
        return action

    if not community.has_owner_condition():
        action.resolution.approve_action(pipeline="foundational", approved_role=matched_role)
        return action

    condition_data = check_conditional(action, community, "owner")
    action = apply_condition_data_to_action(action, condition_data, "foundational", matched_role)
    return action


def check_specific_permission(permission, action):
    """Helper method called by specific permissions pipeline.  Given a permission, checks to see if its active,
    if it has the right configuration, that the actor satisfies the permission, in that order."""

    if not permission.is_active:
        return False, None

    if not check_configuration(action, permission):
        return False, None
    
    permClient = PermissionResourceClient(actor="system", target=action.target)
    return permClient.actor_satisfies_permission(actor=action.actor, permission=permission)
    

def specific_permission_pipeline(action):
    """Checks the target for specific permissions matching the change type and configuration of the action.
    If found, it goes through any matches and checks to see that the actor satisfies the permission. For the 
    permissions the actor does satisfy, we look for conditions. If any permissions have no condition, the action 
    is approved.

    Before checking conditions, we first look to see whether the target is nested on another object which may 
    have permissions set on it. For instance, the target may be a post in a forum, where the forum has an 
    'edit post' permission that applies across all posts. We get additional permissions from that nested object 
    and run them through the same process (checking change type and configuration; checking the actor satisfies 
    the permission; checking if a condition exists).

    If none of the nested permissions immediately passes, we start trying permissions with conditions.  If any
    are approved, the action is approved.  If any are waiting, the action is tentatively set to waiting. 
    If none are approved or waiting, the action is rejected.
    """

    permissionClient = PermissionResourceClient(system=True, target=action.target)

    conditioned_permissions = []

    # Get and check target level permissions
    for permission in permissionClient.get_specific_permissions(change_type=action.change.get_change_type()):
        passes, matched_role = check_specific_permission(permission, action)
        if passes:
            permission.matched_role = matched_role
            if permission.has_condition():
                conditioned_permissions.append(permission)
            else:
                action.resolution.approve_action(pipeline="specific", approved_role=matched_role)
                return action

    # If we're still here, that means nothing matched without a condition, so now we look for nested permissions
    for nested_object in action.target.get_nested_objects():  
        permissionClient.set_target(target=nested_object)
        for permission in permissionClient.get_specific_permissions(change_type=action.change.get_change_type()):
            passes, matched_role = check_specific_permission(permission, action)
            if passes:
                permission.matched_role = matched_role
                if permission.has_condition():
                    conditioned_permissions.append(permission)
                else:
                    action.resolution.approve_action(pipeline="specific", approved_role=matched_role)
                    return action   

    # There's no permissions passing without conditions, so now we check conditions, starting with the target level
    for permission in conditioned_permissions:

        condition_data = check_conditional(action, permission)

        cname = condition_data["condition_item"].get_model_name() if condition_data["condition_item"] else "not created"

        if condition_data["condition_status"] == "approved":
            action.resolution.approve_action(pipeline="specific", approved_role=permission.matched_role,
                approved_condition=cname)
            return action
        elif condition_data["condition_status"] == "waiting":
            log = f"waiting on condition '{cname}' for permission {permission} (role {permission.matched_role})"
            action.resolution.set_waiting(pipeline="specific", log=log)
        elif condition_data["condition_status"] == "not created":
            log = f"waiting on uncreated condition for permission {permission} (role {permission.matched_role})"
            action.resolution.set_waiting(pipeline="specific", log=log)
            action.resolution.conditions.append(condition_data["source_id"])
        elif condition_data["condition_status"] == "rejected":
            log=f"action passed permission {permission} but was rejected by condition {cname}"
            action.resolution.reject_action(pipeline="specific", log=log)
    
    return action


def governing_permission_pipeline(action):

    communityClient = CommunityClient(system=True)
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)

    has_authority, matched_role = communityClient.has_governing_authority(actor=action.actor)
    if not has_authority:
        action.resolution.reject_action(pipeline="governing")
        return action   

    if not community.has_governor_condition():
        action.resolution.approve_action(pipeline="governing", approved_role=matched_role)
        return action
    
    condition_data = check_conditional(action, community, "governor")
    action = apply_condition_data_to_action(action, condition_data, "governing", matched_role)
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
    if action.change.get_change_type() in foundational_changes() or action.target.foundational_permission_enabled:
        return foundational_permission_pipeline(action)

    # Check that object allows us to use governing permission, if yes, try governing pipeline
    if action.target.governing_permission_enabled:
        action = governing_permission_pipeline(action)

    # If action was approved by the governing pipeline, return it, otherwise try specific permission pipeline too
    if action.resolution.governing_status == "approved":
        return action
    return specific_permission_pipeline(action)
