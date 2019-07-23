from concord.actions.state_changes import foundational_changes
from concord.conditionals.client import CommunityConditionalClient, PermissionConditionalClient
from concord.communities.client import CommunityClient
from concord.permission_resources.client import PermissionResourceClient


def check_conditional(action, condition_template, called_by, role=None):

    # If condition template is null, no condition set on permission - approve + return.
    if condition_template is None:
        action.approve_action(resolved_through=called_by, role=role)
        return action

    # Does this action already have a condition action instance?  If no, make one.
    conditionalClient = PermissionConditionalClient(actor="system")
    condition_item = conditionalClient.get_or_create_condition(action=action,
        condition_template=condition_template)

    condition_status = condition_item.condition_status()

    if condition_status == "approved":        
        action.approve_action(resolved_through=called_by, role=role,
            condition=condition_template.condition_type)
    elif condition_status == "rejected":
        action.reject_action(resolved_through=called_by, role=role,
            condition=condition_template.condition_type,
            log="action passed permission but rejected on condition")
    if condition_status == "waiting":
        action.status = "waiting"
        action.log="action passed permission pipeline " + called_by + " but waiting on condition " + condition_template.condition_type
    return action


def shortcut_for_individual_ownership(action, called_by):
    if action.target.owner_type == "ind":
        if action.actor == action.target.owner:
            action.approve_action(resolved_through=called_by, log="approved via individual ownership shortcut")
        else:
            action.reject_action(log="individual owner of target does not match actor")
        return action


def foundational_permission_pipeline(action):

    individual_result = shortcut_for_individual_ownership(action, called_by="foundational")
    if individual_result:
        return individual_result
   
    communityClient = CommunityClient(actor="system") 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_foundational_authority(actor=action.actor)
    if not has_authority:
        action.reject_action(resolved_through="foundational", log="actor does not have foundational authority")
        return action

    # Check for conditions
    conditionalClient = CommunityConditionalClient(actor="system", target=community)
    condition_template = conditionalClient.get_condition_template_for_owner()
    return check_conditional(action, condition_template, called_by="foundational", role=matched_role)


def find_specific_permissions(action):
    """Returns matching permission or None."""
    permissionClient = PermissionResourceClient(actor="system")
    permissionClient.set_target(action.target)
    return permissionClient.get_specific_permissions(change_type=action.change_type)


def specific_permission_pipeline(action, specific_permissions):

    # If actor does not match specific permission, reject
    
    permissionClient = PermissionResourceClient(actor="system")

    matching_permission = None
    for permission in specific_permissions:
        is_matched, matched_role = permissionClient.actor_matches_permission(actor=action.actor, permission=permission)
        if is_matched:
            matching_permission = permission
            break

    if not matching_permission:
        action.reject_action(resolved_through="specific", log="no matching specific permissions found")
        return action

    # Check for conditions
    conditionalClient = PermissionConditionalClient(actor="system", target=matching_permission)
    condition_template = conditionalClient.get_condition_template()
    return check_conditional(action, condition_template, called_by="specific", 
        role=matched_role)


def governing_permission_pipeline(action):

    individual_result = shortcut_for_individual_ownership(action, called_by="governing")
    if individual_result:
        return individual_result

    communityClient = CommunityClient(actor="system") 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority, matched_role = communityClient.has_governing_authority(actor=action.actor)
    if not has_authority:
        action.reject_action(resolved_through="governing", log="actor does not have governing authority")
        return action  

    # Check for conditions
    conditionalClient = CommunityConditionalClient(actor="system", target=community)
    condition_template = conditionalClient.get_condition_template_for_governor()
    return check_conditional(action, condition_template, called_by="governing", role=matched_role)


def has_permission(action):

    # Check for criteria indicating we should use the foundational permission pipeline
    if action.change_type in foundational_changes() or action.target.foundational_permission_enabled:
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


