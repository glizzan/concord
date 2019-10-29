from django.contrib.auth.models import User

from concord.actions.state_changes import foundational_changes
from concord.conditionals.client import CommunityConditionalClient, PermissionConditionalClient
from concord.communities.client import CommunityClient
from concord.permission_resources.client import PermissionResourceClient
from concord.permission_resources.utils import check_configuration


def check_conditional(action, condition_template, called_by, role=None):

    # If condition template is null, no condition set on permission - approve + return.
    if condition_template is None:
        action.approve_action(resolved_through=called_by, role=role)
        return action

    # Does this action already have a condition action instance?  If no, make one.
    conditionalClient = PermissionConditionalClient(system=True)
    condition_item = conditionalClient.get_or_create_condition(action=action,
        condition_template=condition_template)

    condition_status = condition_item.condition_status()

    if condition_status == "approved":
        log = "action approved by condition of type %s" % condition_template.condition_type
        action.approve_action(resolved_through=called_by, role=role,
            condition=condition_template.condition_type, log=log)
    elif condition_status == "rejected":
        log = "action passed permission but rejected by type %s" % condition_template.condition_type
        action.reject_action(resolved_through=called_by, role=role,
            condition=condition_template.condition_type, log=log)
    if condition_status == "waiting":
        action.status = "waiting"
        action.log="action passed permission pipeline " + called_by + " but waiting on condition " + condition_template.condition_type
    return action


def foundational_permission_pipeline(action):
   
    communityClient = CommunityClient(system=True) 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_foundational_authority(actor=action.actor)
    if not has_authority:
        action.reject_action(resolved_through="foundational", log="actor does not have foundational authority")
        return action

    # Check for conditions
    conditionalClient = CommunityConditionalClient(system=True, target=community)
    condition_template = conditionalClient.get_condition_template_for_owner()
    return check_conditional(action, condition_template, called_by="foundational", role=matched_role)


def find_specific_permissions(action):
    """Returns matching permission or None."""
    permissionClient = PermissionResourceClient(system=True)
    permissionClient.set_target(action.target)
    specific_permissions = []
    for permission in permissionClient.get_specific_permissions(change_type=action.change.get_change_type()):
        # Check configuration returns false only if the permission has a configuration which the action doesn't satisfy
        is_relevant = check_configuration(action, permission)
        if is_relevant:
            specific_permissions.append(permission)
    return specific_permissions


def specific_permission_pipeline(action, specific_permissions):

    # If actor does not match specific permission, reject
    
    permissionClient = PermissionResourceClient(system=True)

    matching_permission = None
    for permission in specific_permissions:
        is_matched, matched_role = permissionClient.actor_satisfies_permission(action=action, permission=permission)
        if is_matched:
            matching_permission = permission
            break

    if not matching_permission:
        action.reject_action(resolved_through="specific", log="no matching specific permissions found")
        return action

    # Check for conditions
    conditionalClient = PermissionConditionalClient(system=True, target=matching_permission)
    condition_template = conditionalClient.get_condition_template()
    return check_conditional(action, condition_template, called_by="specific", 
        role=matched_role)


def governing_permission_pipeline(action):

    communityClient = CommunityClient(system=True)
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_governing_authority(actor=action.actor)
    if not has_authority:
        action.reject_action(resolved_through="governing", log="actor does not have governing authority")
        return action  

    # Check for conditions
    conditionalClient = CommunityConditionalClient(system=True, target=community)
    condition_template = conditionalClient.get_condition_template_for_governor()
    return check_conditional(action, condition_template, called_by="governing", role=matched_role)


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

    action.reject_action(log="action did not meet any permission criteria")
    return action


