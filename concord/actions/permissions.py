from collections import namedtuple

from django.contrib.auth.models import User

from concord.actions.state_changes import foundational_changes
from concord.conditionals.client import CommunityConditionalClient, PermissionConditionalClient
from concord.communities.client import CommunityClient
from concord.permission_resources.client import PermissionResourceClient
from concord.permission_resources.utils import check_configuration


def check_conditional(action, condition_template):

    # If condition template is null, no condition set on permission - approve + return.
    if condition_template is None:
        return action, "no_template"

    # Does this action already have a condition action instance?  If no, make one.
    conditionalClient = PermissionConditionalClient(system=True)
    condition_item = conditionalClient.get_or_create_condition(action=action,
        condition_template=condition_template)

    return action, condition_item.condition_status()


def foundational_permission_pipeline(action):
   
    communityClient = CommunityClient(system=True) 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_foundational_authority(actor=action.actor)
    if not has_authority:
        action.resolution.reject_action(resolved_through="foundational", log="actor does not have foundational authority")
        return action

    # Check for conditions
    conditionalClient = CommunityConditionalClient(system=True, target=community)
    condition_template = conditionalClient.get_condition_template_for_owner()
    action, condition_status = check_conditional(action, condition_template)

    # Update action
    if condition_status == "no_template":
        action.resolution.approve_action(resolved_through="foundational", role=matched_role, 
            log="action approved via foundational pipeline with with no condition set")
    elif condition_status == "approved":
        action.resolution.approve_action(resolved_through="foundational", role=matched_role, 
            condition=condition_template.condition_name(),
            log="action approved via foundational pipeline with condition %s" % str(condition_template))
    elif condition_status == "rejected": 
        action.resolution.reject_action(resolved_through="foundational", role=matched_role, 
            condition=condition_template.condition_name(),
            log="action passed foundational pipeline but was rejected by condition %s" % str(condition_template))
    elif condition_status == "waiting":
        action.resolution.status = "waiting"
        action.log = "action passed foundational pipeline, now waiting on condition " + str(condition_template)
    
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
    conditionalClient = PermissionConditionalClient(system=True)

    # Get and check target level permissions
    permissions = get_permissions(permissionClient, action.target, action)
    matching_permissions = []
    for permission in permissions:
        matched, matched_role = permissionClient.actor_satisfies_permission(actor=action.actor, permission=permission)
        if matched:
            matching_permissions.append(PermStore(permission=permission, matched_role=matched_role))
       
    # Go through matching target level permissions and look for any that pass without conditions
    for permission in matching_permissions:
        conditionalClient.set_target(permission.permission)
        condition_template = conditionalClient.get_condition_template()
        if not condition_template:
            action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
                log="action approved via specific pipeline with with no condition set")
            return action
        else:
            permission.condition = condition_template
    
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
        conditionalClient.set_target(permission.permission)
        condition_template = conditionalClient.get_condition_template()
        if not condition_template:
            action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
                log="action approved via specific pipeline with with no condition set")
            return action
        else:
            permission.condition = condition_template

    # There's no permissions passing without conditions, so now we check conditions, starting with the target level
    waiting_on_permission = False
    temp_log = []
    for permission in matching_permissions + matching_nested_permissions:

        action, conditional_status = check_conditional(action, permission.condition)

        if conditional_status == "approved":
            action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
                condition=permission.condition.condition_name(),
                log="action approved via specific pipeline with with condition %s" % str(permission.condition))
            return action
        elif conditional_status == "waiting":
            waiting_on_permission = True
            temp_log.append("waiting on condition %s for permission %s (role %s)" % (str(permission.condition),
                permission.permission, permission.matched_role))
        elif conditional_status == "rejected":
            temp_log.append("rejected by condition %s for permission %s (role %s)" % (str(permission.condition),
                permission.permission, permission.matched_role))

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

    # Check for conditions
    conditionalClient = CommunityConditionalClient(system=True, target=community)
    condition_template = conditionalClient.get_condition_template_for_governor()
    action, condition_status =  check_conditional(action, condition_template)

    # Update action
    if condition_status == "no_template":
        action.resolution.approve_action(resolved_through="governing",  role=matched_role,
            log="action approved via governing pipeline with with no condition set")
    elif condition_status == "approved":
        action.resolution.approve_action(resolved_through="governing", role=matched_role, 
            condition=condition_template.condition_name(),
            log="action approved via governing pipeline with condition %s" % str(condition_template))
    elif condition_status == "rejected": 
        message = "action passed governing pipeline but was rejected by condition %s" % str(condition_template)
        action.resolution.add_to_log(message)
    elif condition_status == "waiting":
        action.resolution.status = "waiting"
        message = "action passed governing pipeline, now waiting on condition " + str(condition_template)
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


