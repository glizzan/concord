from concord.actions.state_changes import foundational_changes


def check_conditional(action, condition_template):

    # Does the permission have a condition?  If no, just approve it.
    if not condition_template:
        return "approved", None

    # Does this action already have a condition action instance?  If no, make one.
    from concord.conditionals.client import PermissionConditionalClient
    conditionalClient = PermissionConditionalClient(actor="system")
    condition_item = conditionalClient.get_or_create_condition(action=action,
        condition_template=condition_template)

    # NOTE: this log statement is not super useful, but maybe we should be getting
    # th elog from condition_status()
    return condition_item.condition_status(), "condition status checked"


def shortcut_for_individual_ownership(action):
    if action.target.owner_type == "ind":
        if action.actor == action.target.owner:
            return "approved", None
        return "rejected", "individual owner of target does not match actor"
    return None, None  


def find_specific_permissions(action):
    # Returns matched permission or None.
    from concord.permission_resources.client import PermissionResourceClient
    permissionClient = PermissionResourceClient(actor="system")
    permissionClient.set_target(action.target)
    return permissionClient.get_specific_permissions(change_type=action.change_type)


def foundational_permission_pipeline(action):

    individual_result, log = shortcut_for_individual_ownership(action)
    if individual_result:
        return individual_result, log

    from concord.communities.client import CommunityClient
    communityClient = CommunityClient(actor="system") 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority = communityClient.has_foundational_authority(actor=action.actor)
    if not has_authority:
        return "rejected", "actor does not have foundational authority"   

    from concord.conditionals.client import CommunityConditionalClient
    conditionalClient = CommunityConditionalClient(actor="system", target=community)
    condition_template = conditionalClient.get_condition_template_for_owner()

    return check_conditional(action, condition_template)


def specific_permission_pipeline(action, specific_permissions):

    # If actor does not match specific permission, reject
    from concord.permission_resources.client import PermissionResourceClient
    permissionClient = PermissionResourceClient(actor="system")

    matching_permission = None
    for permission in specific_permissions:
        if permissionClient.actor_matches_permission(actor=action.actor, permission=permission):
            matching_permission = permission
            break

    if not matching_permission:
        return "rejected", "no matching specific permissions found"

    from concord.conditionals.client import PermissionConditionalClient
    conditionalClient = PermissionConditionalClient(actor="system")
    conditionalClient.set_target(target=matching_permission)
    condition_template = conditionalClient.get_condition_template()

    return check_conditional(action, condition_template)


def governing_permission_pipeline(action):
    individual_result, log = shortcut_for_individual_ownership(action)
    if individual_result:
        return individual_result, log

    from concord.communities.client import CommunityClient
    communityClient = CommunityClient(actor="system") 
    community = communityClient.get_owner(owned_object=action.target)
    communityClient.set_target(target=community)
    has_authority = communityClient.has_governing_authority(actor=action.actor)
    if not has_authority:
        return "rejected", "actor does not have governing authority"   

    from concord.conditionals.client import CommunityConditionalClient
    conditionalClient = CommunityConditionalClient(actor="system", target=community)
    condition_template = conditionalClient.get_condition_template_for_governor()

    return check_conditional(action, condition_template)


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

    # If none of the above is enabled, reject action
    return "rejected", "action did not meet any permission criteria"

