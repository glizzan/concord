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


def find_specific_permissions(action):
    """Returns matching permissions or empty list."""
    permissionClient = PermissionResourceClient(system=True)
    permissionClient.set_target(action.target)
    specific_permissions = []
    for permission in permissionClient.get_specific_permissions(change_type=action.change.get_change_type()):
        if not permission.is_active:
            continue       
        if check_configuration(action, permission):
            specific_permissions.append(permission)
    return specific_permissions


def specific_permission_pipeline(action, specific_permissions):
    """Goes through matching specific permissions.  First, it checks to see that the actor satisfies the permission.
    If the actor doesn't satisfy any permissions, the actoin is rejected.  For the permissions the actor does 
    satisfy, we look for conditions:

        * If any permissions have no condition, the action is approved
        * If any of the conditions are approved, the action is approved
        * If none are approved, but any are waiting, the action is waiting; 
        * If none are approved or waiting, the action is rejected."""
    
    permissionClient = PermissionResourceClient(system=True)

    matching_permissions = {}
    for permission in specific_permissions:
        is_matched, matched_role = permissionClient.actor_satisfies_permission(actor=action.actor, permission=permission)
        if is_matched:
            matching_permissions.update({permission : matched_role})

    if not matching_permissions:    # If actor does not match specific permission, reject
        action.resolution.reject_action(resolved_through="specific", log="no matching specific permissions found")
        return action

    waiting_on_permission = False
    temp_log = []

    for matched_perm, matched_role in matching_permissions.items():

        # Check for conditions
        conditionalClient = PermissionConditionalClient(system=True, target=matched_perm)
        condition_template = conditionalClient.get_condition_template()
        action, conditional_status = check_conditional(action, condition_template)

        if conditional_status == "no_template":
            action.resolution.approve_action(resolved_through="specific", role=matched_role,
                log="action approved via specific pipeline with with no condition set")
        elif conditional_status == "approved":
            action.resolution.approve_action(resolved_through="specific", role=matched_role,
                condition=condition_template.condition_name(),
                log="action approved via specific pipeline with with condition %s" % str(condition_template))
        elif conditional_status == "waiting":
            waiting_on_permission = True
            temp_log.append("waiting on condition %s for permission %s (role %s)" % (str(condition_template),
                matched_perm, matched_role))
        elif conditional_status == "rejected":
            temp_log.append("rejected by condition %s for permission %s (role %s)" % (str(condition_template),
                matched_perm, matched_role))

        # If permission is accepted, return, otherwise continue with loop
        if action.resolution.status == "approved":
            return action

    # If after looping through matching permissions we're waiting on a permission, the whole action
    # is set to waiting, otherwise reject.
    if waiting_on_permission:
        action.resolution.status = "waiting"
        action.resolution.add_to_log("; ".join(temp_log))
        return action
    else:

        # Hack to save info if only one matched permission
        if len(matching_permissions) == 1:
            condition = condition_template.condition_name()
            role = matched_role
        else:
            condition, role = None, None
        action.resolution.reject_action(resolved_through="specific", condition=condition, role=role,
            log="; ".join(temp_log))
        return action


def governing_permission_pipeline(action):

    communityClient = CommunityClient(system=True)
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_governing_authority(actor=action.actor)
    if not has_authority:
        action.resolution.reject_action(resolved_through="governing", log="actor does not have governing authority")
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
        action.resolution.reject_action(resolved_through="governing", role=matched_role, 
            condition=condition_template.condition_name(),
            log="action passed governing pipeline but was rejected by condition %s" % str(condition_template))
    elif condition_status == "waiting":
        action.resolution.status = "waiting"
        action.log = "action passed governing pipeline, now waiting on condition " + str(condition_template)
    
    return action

def has_permission(action):

    # Check for criteria indicating we should use the foundational permission pipeline
    if action.change.get_change_type() in foundational_changes() or action.target.foundational_permission_enabled:
        return foundational_permission_pipeline(action)

    # Check for existence of specific permission, if found use specific permission pipeline
    specific_permissions = find_specific_permissions(action)
    if specific_permissions:
        return specific_permission_pipeline(action, specific_permissions)

    # Check that object allows us to use governing permission, if yes, use governing pipeline
    if action.target.governing_permission_enabled:
        return governing_permission_pipeline(action)

    action.resolution.reject_action(log="action did not meet any permission criteria")
    return action


