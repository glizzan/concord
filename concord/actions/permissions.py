"""
This module contains the logic for checking if an action has a given permission.  It does not change the database
or even the state of the action passed in - instead, it returns one or more Resolution object containing 
information about whether or not the action would pass with or without conditions and, if it would trigger 
conditions, the type and the pk of the condition_template with more data.

Most commonly used by the take_action method of an action, typical usage involves:

- calling has_permission and seeing if it passes
- if it passes, call implement(), or if it's rejected without conditions, reject
- if it does not pass but has conditions, create the first condition in the list
- call has_permission again
- repeat until no more conditions are left
"""
# from collections import namedtuple

# from concord.actions.state_changes import foundational_changes
# from concord.conditionals.client import CommunityConditionalClient, PermissionConditionalClient
# from concord.communities.client import CommunityClient
# from concord.permission_resources.client import PermissionResourceClient
from concord.actions.customfields import Resolution
from concord.permission_resources.utils import check_configuration

'''
List of changes outside of permissions.py to be made:
- action object passed in needs is_foundational_change(), is_governing_change() passed in
- has_permission caller needs to handle calling and checking conditions, so need to fix action.take_action
    and what happens in action container (and do a search for has_permission calls just in case)
- refactored conditionalclients into one client
- refactored conditions to have a template attribute with no default, changes how we look up condition items as well
as create them :/

'''


def check_conditional(clif, target, leadership_type=None):
    """Given an action, checks if it would trigger a condition and, if so, returns data about the condition
    that would be triggered."""

    # Get condition template
    clif.conditions.set_target(target=target)
    condition_template = clif.conditions.get_condition_template(leadership_type=leadership_type)
    
    # If condition template is null, no condition set on permission
    if condition_template is None:
        return False, None

    condition_item = clif.conditions.get_condition_item_for_action_and_template(action=action, condition_template=condition_template,
        condition_type=condition_template.condition_data.condition_type)

    # Otherwise return info
    return True, { 
        "template_pk": condition_template.pk, 
        "type": condition_template.condition_data.condition_type,
        "condition_pk": condition_item.pk if condition_item else None,
        "condition_status": condition_item.condition_status() if condition_item else None                
        }


def update_resolution_given_condition_info(condition_info, resolution, rejection_is_final=False):

    resolution.condition_list.append(condition_info)

    if condition_info["condition_status"] == "approved":
        resolution.approve_action(log=
            f"action passed permsision and {condition_info['type']} (pk: {condition_info['condition_pk']})")

    if condition_info["condition_status"] == "rejected" and rejection_is_final:
        resolution.reject_action(log=
            f"action passed permsision but failed {condition_info['type']} (pk: {condition_info['condition_pk']})")
    
    if condition_info["condition_status"] == "waiting":
        resolution.status = "waiting"
        resolution.log = f"action waiting on condition {condition_info['pk']}"

    return resolution


def foundational_permission_pipeline(action, clif):

    # set target of community client to the owner of the action target
    clif.communities.set_target(target=clif.communities.get_owner(owned_object=action.target))
   
    has_authority, matched_role = clif.communities.has_foundational_authority(actor=action.actor)
    if not has_authority:
        return Resolution(status="rejected", resolved_through="foundational", 
            log="actor does not have foundational authority")
        
    has_condition, condition_info = check_conditional(clif, clif.communities.target, "owner")  

    if has_condition:
        resolution = Resolution(status="unknown", role=matched_role, resolved_through="foundational")
        return update_resolution_given_condition_info(condition_info, resolution, True)
    else:
        return Resolution(status="approved", resolved_through="foundational", role=matched_role,
            log="action approved via foundational pipeline with with no condition set")
        

def governing_permission_pipeline(action, clif):

    # set target of community client to the owner of the action target
    clif.communities.set_target(target=clif.communities.get_owner(owned_object=action.target))

    has_authority, matched_role = clif.communities.has_governing_authority(actor=action.actor)
    if not has_authority:
        return Resolution(status="rejected", resolved_through="governing", 
            log="actor does not have governing authority")

    has_condition, condition_info = check_conditional(clif, clif.communities.target, "governor")

    if has_condition:
        resolution = Resolution(status="unknown", role=matched_role, resolved_through="governing")
        return update_resolution_given_condition_info(condition_info, resolution, True)
    else:
        return Resolution(status="approved", resolved_through="governing", role=matched_role,
            log="action approved via governing pipeline with with no condition set")


def check_specific_permission(clif, permission, action, resolution):
    """Checks a given permission to see if it's active and has the right configuration.  If it does, checks that
    the actor satisfies the permission. If they do, finally, looks for a condition and if there is no condition
    set, approves the action.  Always returns a boolean indicating if the action was approved along with the 
    resolution object, which may have been updated."""

    if not permission.is_active:
        return False, resolution
    if not check_configuration(action, permission):
        return False, resolution
    
    matched, matched_role = clif.permissions.actor_satisfies_permission(actor=action.actor, permission=permission)
    if not matched:
        return False, resolution
    
    has_condition, condition_info = check_conditional(clif, permission) 

    if has_condition:
        resolution.role = matched_role
        return update_resolution_given_condition_info(condition_info, resolution, False)
    else:
        resolution.approve_action(role=matched_role, log="action approved via specific pipeline with with no condition set")
        return True, resolution 
        

def specific_permission_pipeline(action, clif):
    """Checks the target for specific permissions matching the change type and configuration of the action.
    If found, it goes through any matches and checks to see that the actor satisfies the permission. For the 
    permissions the actor does satisfy, we look for conditions. If any permissions have no condition, the action 
    is approved.

    Once the action is approved, the pipeline returns. Otherwise, we keep storing condition information to pass back
    to the caller. If none of the target's permissions are approved unconditionally, we look to see whether the
    target is nested on another object which may have permissions set on it.  For instance, the target may be a post in a forum, where the forum has an 
    'edit post' permission that applies across all posts. We get additional permissions from that nested object 
    and run them through the same process (checking change type and configuration; checking the actor satisfies 
    the permission; checking if a condition exists).

    If at the end of this, there are no conditions (and, obviously, not approved unconditional approvals), the action
    resolution status is set to rejected.
    """

    resolution = Resolution(status="unknown", resolved_through="specific")

    # Try the target itself first
    clif.permissions.set_target(target=action.target)  # set target of permissions client to action's target
    for permission in clif.permissions.get_specific_permissions(change_type=action.change.get_change_type()):
        permission_passes, resolution = check_specific_permission(clif, permission, action, resolution)
        if permission_passes:
            return resolution

    # If we're still here, try nested permissions
    for nested_object in action.target.get_nested_objects():
        clif.permissions.set_target(nested_object)
        for permission in clif.permissions.get_specific_permissions(change_type=action.change.get_change_type())
            permission_passes, resolution = check_specific_permission(clif, permission, action, resolution)
            if permission_passes:
                return resolution

    # If after all this, status is "unknown" rather than "waiting", it means no action passes conditionally or
    # unconditionally, and we should reject it, otherwise return resolution as is.
    if resolution.status == "unknown":
        resolution.reject_action(log="actor doesn't pass any permissions")
    return resolution

        
def has_permission(action, clif):
    """
    Takes in an action and a client interface (clif for short). Checks whether the action passes or fails the 
    permissions pipeline without conditions or, if conditions exist, generates a list of conditions. Passes
    this information back to the caller to decide whether to trigger the conditions, implement the actions, etc.
    Typically if conditions are passed back, the caller triggers the conditions and calls has_permission again.

    If the action is a foundational change, we only run that part of the pipeline. If it's a governing change 
    *and* the action would be approved via the governing pipeline, we skip the specific permission pipeline, 
    otherwise run it. Information is returned as a tuple of Resolution objects with format:
    
    (FoundationalResolution, GoverningResolution, SpecificResolution)

    Note that we do not make ANY changes to the db.
    """

    if action.is_foundational_change(clif):
        foundational_resolution = foundational_permission_pipeline(action, clif)
        return (foundational_resolution, None, None)

    governing_resolution = None  # initialize
    if action.is_governing_change(clif):
        governing_resolution = governing_permission_pipeline(action, clif)

    specific_resolution = None  # initialize
    if not governing_resolution or governing_resolution.status != "approved":
        specific_resolution = specific_permission_pipeline(action, clif)

    return (None, governing_resolution, specific_resolution)









#####################################################


# def check_conditional(action, condition_template):

#     # If condition template is null, no condition set on permission - approve + return.
#     if condition_template is None:
#         return action, "no_template"

#     # Don't actually create condition if action is a mock
#     if hasattr(action, "is_mock") and action.is_mock == True:
#         return action, "waiting"

#     # Does this action already have a condition action instance?  If no, make one.
#     conditionalClient = PermissionConditionalClient(system=True)
#     condition_item = conditionalClient.get_or_create_condition(action=action,
#         condition_template=condition_template)   # CLIENT_CALL  # DB_CALL

#     return action, condition_item.condition_status()


# def foundational_permission_pipeline(action):
   
#     communityClient = CommunityClient(system=True)   # CLIENT_CALL
#     community = communityClient.get_owner(owned_object=action.target)
#     communityClient.set_target(target=community)
#     has_authority, matched_role = communityClient.has_foundational_authority(actor=action.actor)
#     if not has_authority:
#         action.resolution.reject_action(resolved_through="foundational", log="actor does not have foundational authority")
#         return action

#     # Check for conditions
#     conditionalClient = CommunityConditionalClient(system=True, target=community)    # CLIENT_CALL
#     condition_template = conditionalClient.get_condition_template_for_owner()
#     action, condition_status = check_conditional(action, condition_template)

#     # Update action
#     if condition_status == "no_template":   
#         action.resolution.approve_action(resolved_through="foundational", role=matched_role, 
#             log="action approved via foundational pipeline with with no condition set")
#     elif condition_status == "approved":
#         action.resolution.approve_action(resolved_through="foundational", role=matched_role, 
#             condition=condition_template.condition_name(),
#             log="action approved via foundational pipeline with condition %s" % str(condition_template))
#     elif condition_status == "rejected": 
#         action.resolution.reject_action(resolved_through="foundational", role=matched_role, 
#             condition=condition_template.condition_name(),
#             log="action passed foundational pipeline but was rejected by condition %s" % str(condition_template))
#     elif condition_status == "waiting":
#         action.resolution.status = "waiting"
#         action.resolution.log = "action passed foundational pipeline, now waiting on condition " + str(condition_template)
    
#     return action


# def get_permissions(clif, target, action):
#     """Gets permissions matching the action change_type, given a target."""
#     vetted_permissions = []
#     clif.permissions.set_target(target)
#     for permission in clif.permissions.get_specific_permissions(change_type=action.change.get_change_type()):
#         if permission.is_active and check_configuration(action, permission):
#             vetted_permissions.append(permission)
#     return vetted_permissions


# class PermStore(object):
#     """Helper class used in specific_permission_pipeline"""
#     def __init__(self, permission, matched_role, condition=None):
#         self.permission = permission
#         self.matched_role = matched_role
#         self.condition = condition


# def specific_permission_pipeline(action):
#     """Checks the target for specific permissions matching the change type and configuration of the action.
#     If found, it goes through any matches and checks to see that the actor satisfies the permission. For the 
#     permissions the actor does satisfy, we look for conditions. If any permissions have no condition, the action 
#     is approved.

#     Before checking conditions, we first look to see whether the target is nested on another object which may 
#     have permissions set on it. For instance, the target may be a post in a forum, where the forum has an 
#     'edit post' permission that applies across all posts. We get additional permissions from that nested object 
#     and run them through the same process (checking change type and configuration; checking the actor satisfies 
#     the permission; checking if a condition exists).

#     If none of the nested permissions immediately passes, we start trying permissions with conditions.  If any
#     are approved, the action is approved.  If any are waiting, the action is tentatively set to waiting. 
#     If none are approved or waiting, the action is rejected.
#     """
    
#     permissionClient = PermissionResourceClient(system=True)
#     conditionalClient = PermissionConditionalClient(system=True)

#     # Get and check target level permissions    # CLIENT_CALL
#     permissions = get_permissions(permissionClient, action.target, action)
#     matching_permissions = []
#     for permission in permissions:
#         matched, matched_role = permissionClient.actor_satisfies_permission(actor=action.actor, permission=permission)
#         if matched:
#             matching_permissions.append(PermStore(permission=permission, matched_role=matched_role))
       
#     # Go through matching target level permissions and look for any that pass without conditions
#     for permission in matching_permissions:
#         conditionalClient.set_target(permission.permission)
#         condition_template = conditionalClient.get_condition_template()   # CLIENT_CALL
#         if not condition_template:
#             action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
#                 log="action approved via specific pipeline with with no condition set")
#             return action
#         else:
#             permission.condition = condition_template
    
#     # If we're still here, that means nothing matched without a condition, so now we look for nested permissions
#     matching_nested_permissions = []
#     for nested_object in action.target.get_nested_objects():  #FIXME: need to implement this!
#         permissions = get_permissions(permissionClient, nested_object, action)   # CLIENT_CALL
#         for permission in permissions:
#             matched, matched_role = permissionClient.actor_satisfies_permission(actor=action.actor, permission=permission)
#             if matched:
#                 matching_nested_permissions.append(PermStore(permission=permission, matched_role=matched_role))

#     # Go through matching nested permissions and look for any that pass without conditions
#     for permission in matching_nested_permissions:
#         conditionalClient.set_target(permission.permission)
#         condition_template = conditionalClient.get_condition_template()   # CLIENT_CALL
#         if not condition_template:
#             action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
#                 log="action approved via specific pipeline with with no condition set")
#             return action
#         else:
#             permission.condition = condition_template

#     # There's no permissions passing without conditions, so now we check conditions, starting with the target level
#     waiting_on_permission = False
#     temp_log = []
#     for permission in matching_permissions + matching_nested_permissions:

#         action, conditional_status = check_conditional(action, permission.condition)

#         if conditional_status == "approved":
#             action.resolution.approve_action(resolved_through="specific", role=permission.matched_role,
#                 condition=permission.condition.condition_name(),
#                 log="action approved via specific pipeline with with condition %s" % str(permission.condition))
#             return action
#         elif conditional_status == "waiting":
#             waiting_on_permission = True
#             temp_log.append("waiting on condition %s for permission %s (role %s)" % (str(permission.condition),
#                 permission.permission, permission.matched_role))
#         elif conditional_status == "rejected":
#             temp_log.append("rejected by condition %s for permission %s (role %s)" % (str(permission.condition),
#                 permission.permission, permission.matched_role))

#     # If after looping through all permissions we're waiting on one or more permissions, set status to waiting.
#     if waiting_on_permission:
#         action.resolution.status = "waiting"
#         action.resolution.add_to_log("; ".join(temp_log))
#         return action

#     # If matching specific permissions were found, mark as rejected
#     if len(matching_permissions + matching_nested_permissions) > 0:
#         action.resolution.add_to_log("; ".join(temp_log))
#         action.resolution.reject_action(resolved_through="specific")
        
#     return action


# def governing_permission_pipeline(action):

#     communityClient = CommunityClient(system=True)
#     community = communityClient.get_owner(owned_object=action.target)
#     communityClient.set_target(target=community)
#     has_authority, matched_role = communityClient.has_governing_authority(actor=action.actor)   # CLIENT_CALL

#     if not has_authority:
#         return action  

#     # Check for conditions
#     conditionalClient = CommunityConditionalClient(system=True, target=community)
#     condition_template = conditionalClient.get_condition_template_for_governor()   # CLIENT_CALL
#     action, condition_status =  check_conditional(action, condition_template)

#     # Update action
#     if condition_status == "no_template":
#         action.resolution.approve_action(resolved_through="governing",  role=matched_role,
#             log="action approved via governing pipeline with with no condition set")
#     elif condition_status == "approved":
#         action.resolution.approve_action(resolved_through="governing", role=matched_role, 
#             condition=condition_template.condition_name(),
#             log="action approved via governing pipeline with condition %s" % str(condition_template))
#     elif condition_status == "rejected": 
#         message = "action passed governing pipeline but was rejected by condition %s" % str(condition_template)
#         action.resolution.add_to_log(message)
#     elif condition_status == "waiting":
#         action.resolution.status = "waiting"
#         message = "action passed governing pipeline, now waiting on condition " + str(condition_template)
#         action.resolution.add_to_log(message)
    
#     return action


# def has_permission(action, client):
#     """has_permission directs the flow of logic in the permissions pipeline.  
    
#     If the foundational permission is enabled or the change type is a foundational change (like change_owner), 
#     we go into the foundational permission pipeline and no other pipeline.
    
#     If the governing permission is enabled, we try that pipeline. If the action is approved by the governing 
#     pipeline and we finish with the permission pipeline, otherwise we move on to the last option, the specific 
#     permission pipeline.

#     Note: this structure makes it possible for several conditions to be raised on a single action, which may
#     prove confusing or tedious.
#     """ 

#     # Check for criteria indicating we should use the foundational permission pipeline
#     if action.change.get_change_type() in foundational_changes() or action.target.foundational_permission_enabled:
#         return foundational_permission_pipeline(action)

#     # Check that object allows us to use governing permission, if yes, try governing pipeline
#     if action.target.governing_permission_enabled:
#         action = governing_permission_pipeline(action)
#         if action.resolution.status == "approved":
#             return action

#     # If action wasn't approved by the governing pipeline, try specific permission pipeline
#     action = specific_permission_pipeline(action)
#     if action.resolution.status in ["approved", "waiting"]:
#         return action

#     action.resolution.reject_action(log="action did not meet any permission criteria")
#     return action


