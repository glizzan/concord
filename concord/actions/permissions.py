from collections import namedtuple

from django.contrib.auth.models import User

from concord.actions.state_changes import foundational_changes
from concord.conditionals.client import ConditionalClient
from concord.communities.client import CommunityClient
from concord.permission_resources.client import PermissionResourceClient
from concord.permission_resources.utils import check_configuration


# TODO: need to refactor this so we're not creating conditions in here, or otherwise changing the DB
# should just *get* the condition and check status, no creating it if it's not already there.
def check_conditional(action, community_or_permission, leadership_type=None):

    # Don't actually create condition if action is a mock
    if hasattr(action, "is_mock") and action.is_mock == True:
        class MockConditionitem(object):
            def get_model_name(self):
                return "mock condition"
            def condition_status(self):
                return "waiting"
        return action, MockConditionitem()

    conditionalClient = ConditionalClient(system=True)

    if hasattr(community_or_permission, "is_community") and community_or_permission.is_community:
        condition_item = conditionalClient.get_or_create_condition_on_community(action, community_or_permission, leadership_type)
    else:
        condition_item = conditionalClient.get_or_create_condition_on_permission(action, community_or_permission)

    return action, condition_item


def foundational_permission_pipeline(action):
   
    communityClient = CommunityClient(system=True) 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_foundational_authority(actor=action.actor)

    if not has_authority:
        action.resolution.reject_action(resolved_through="foundational", log="actor does not have foundational authority")
        return action

    if not community.has_owner_condition():
        action.resolution.approve_action(resolved_through="foundational", role=matched_role, 
            log="action approved via foundational pipeline with with no condition set")
        return action

    # Update action based on condition
    action, condition_item = check_conditional(action, community, "owner")

    if condition_item.condition_status() == "approved":
        action.resolution.approve_action(resolved_through="foundational", role=matched_role, 
            condition=condition_item.get_model_name(),
            log=f"action approved via foundational pipeline with condition {condition_item.get_model_name()}")
    elif condition_item.condition_status() == "rejected": 
        action.resolution.reject_action(resolved_through="foundational", role=matched_role, 
            condition=condition_item.get_model_name(),
            log=f"action passed foundational pipeline but was rejected by condition {condition_item.get_model_name()}")
    elif condition_item.condition_status() == "waiting":
        action.resolution.status = "waiting"
        action.resolution.log = f"action passed foundational pipeline, now waiting on condition {condition_item.get_model_name()}"
    
    return action


def get_permissions(permissionClient, target, action):
    """Gets permissions matching the action change_type, given a target."""
    vetted_permissions = []
    permissionClient.set_target(target)
    for permission in permissionClient.get_specific_permissions(change_type=action.change.get_change_type()):
        if permission.is_active and check_configuration(action, permission):
            vetted_permissions.append(permission)
    return vetted_permissions


class PermStore(object):
    """Helper class used in specific_permission_pipeline"""
    def __init__(self, permission, matched_role, condition=None):
        self.permission = permission
        self.matched_role = matched_role
        self.condition = condition


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
    
    permissionClient = PermissionResourceClient(system=True)
    conditionalClient = ConditionalClient(system=True)

    # Get and check target level permissions
    permissions = get_permissions(permissionClient, action.target, action)
    matching_permissions = []
    for permission in permissions:
        matched, matched_role = permissionClient.actor_satisfies_permission(actor=action.actor, permission=permission)
        if matched:
            matching_permissions.append(PermStore(permission=permission, matched_role=matched_role))

    # Go through matching target level permissions and look for any that pass without conditions
    for permission in matching_permissions:
        if not permission.permission.has_condition():
            action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
                log="action approved via specific pipeline with with no condition set")
            return action
    
    # If we're still here, that means nothing matched without a condition, so now we look for nested permissions
    matching_nested_permissions = []
    for nested_object in action.target.get_nested_objects():  #FIXME: need to implement this!
        permissions = get_permissions(permissionClient, nested_object, action)
        for permission in permissions:
            matched, matched_role = permissionClient.actor_satisfies_permission(actor=action.actor, permission=permission)
            if matched:
                matching_nested_permissions.append(PermStore(permission=permission, matched_role=matched_role))

    # Go through matching nested permissions and look for any that pass without conditions
    for permission in matching_nested_permissions:
        if not permission.permission.has_condition():
            action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
                log="action approved via specific pipeline with with no condition set")
            return action

    # There's no permissions passing without conditions, so now we check conditions, starting with the target level
    waiting_on_permission = False
    temp_log = []
    for permission in matching_permissions + matching_nested_permissions:

        if not permission.permission.has_condition():
            continue

        action, condition_item = check_conditional(action, permission.permission)

        if condition_item.condition_status() == "approved":
            action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
                condition=condition_item.get_model_name(),
                log=f"action approved via specific pipeline with with condition {condition_item.get_model_name()}")
            return action
        elif condition_item.condition_status() == "waiting":
            waiting_on_permission = True
            temp_log.append(f"waiting on condition {condition_item.get_model_name()} for permission {permission.permission} (role {permission.matched_role})")            
        elif condition_item.condition_status() == "rejected":
            temp_log.append(f"rejected by condition {condition_item.get_model_name()} for permission {permission.permission} (role {permission.matched_role})")            

    # If after looping through all permissions we're waiting on one or more permissions, set status to waiting.
    if waiting_on_permission:
        action.resolution.status = "waiting"
        action.resolution.add_to_log("; ".join(temp_log))
        return action

    # If matching specific permissions were found, mark as rejected
    if len(matching_permissions + matching_nested_permissions) > 0:
        action.resolution.add_to_log("; ".join(temp_log))
        action.resolution.reject_action(resolved_through="specific")
        
    return action


def governing_permission_pipeline(action):

    communityClient = CommunityClient(system=True)
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_governing_authority(actor=action.actor)

    if not has_authority:
        return action  

    if not community.has_governor_condition():
        action.resolution.approve_action(resolved_through="governing",  role=matched_role,
            log="action approved via governing pipeline with with no condition set")
        return action
    
    action, condition_item = check_conditional(action, community, "governor")
        
    if condition_item.condition_status() == "approved":
        action.resolution.approve_action(resolved_through="governing", role=matched_role, 
            condition=condition_item.get_model_name(),
            log=f"action approved via governing pipeline with condition {condition_item.get_model_name()}")
    elif condition_item.condition_status() == "rejected": 
        message = f"action passed governing pipeline but was rejected by condition {condition_item.get_model_name()}"
        action.resolution.add_to_log(message)
    elif condition_item.condition_status() == "waiting":
        action.resolution.status = "waiting"
        message = f"action passed governing pipeline, now waiting on condition {condition_item.get_model_name()}"
        action.resolution.add_to_log(message)
    
    return action


def has_permission(action):
    """has_permission directs the flow of logic in the permissions pipeline.  
    
    If the foundational permission is enabled or the change type is a foundational change (like change_owner), 
    we go into the foundational permission pipeline and no other pipeline.
    
    If the governing permission is enabled, we try that pipeline. If the action is approved by the governing 
    pipeline and we finish with the permission pipeline, otherwise we move on to the last option, the specific 
    permission pipeline.

    Note: this structure makes it possible for several conditions to be raised on a single action, which may
    prove confusing or tedious.
    """

    if hasattr(action, "bypass_pipeline"):   # Hack to deal with when the system itself is taking an action
        action.resolution.approve_action(resolved_through="system", log="Action targets another action, skip pipeline")
        return action

    # Check for criteria indicating we should use the foundational permission pipeline
    if action.change.get_change_type() in foundational_changes() or action.target.foundational_permission_enabled:
        return foundational_permission_pipeline(action)

    # Check that object allows us to use governing permission, if yes, try governing pipeline
    if action.target.governing_permission_enabled:
        action = governing_permission_pipeline(action)
        if action.resolution.status == "approved":
            return action

    # If action wasn't approved by the governing pipeline, try specific permission pipeline
    action = specific_permission_pipeline(action)
    if action.resolution.status in ["approved", "waiting"]:
        return action

    action.resolution.reject_action(log="action did not meet any permission criteria")
    return action


