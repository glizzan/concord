from concord.actions.state_changes import foundational_changes


def check_conditional(action, condition_template):
    from concord.conditionals.client import ConditionalClient
    conditionalClient = ConditionalClient(actor="system")

    # Does the permission have a condition?  If no, just approve it.
    if not condition_template:
        return "approved"

    # Does this action already have a condition action instance?  If no, make one.
    condition_item = conditionalClient.get_or_create_condition_item(
        condition_template=condition_template, action=action)

    return condition_item.condition_status()


def shortcut_for_individual_ownership(action):
    if action.target.owner_type == "ind":
        if action.actor == action.target.owner:
            return "approved"
        return "rejected"


def find_specific_permissions(action):
    # Returns matched permission or None.
    from concord.permission_resources.client import PermissionResourceClient
    permissionClient = PermissionResourceClient(actor="system")
    return permissionClient.get_specific_permissions(action.target, action.change_type)


def foundational_permission_pipeline(action):

    individual_result = shortcut_for_individual_ownership(action)
    if individual_result:
        return individual_result

    from concord.communities.client import CommunityClient
    communityClient = CommunityClient(actor="system") 
    community = communityClient.get_owner(action.target)
    has_authority = communityClient.has_foundational_authority(community, action.actor)
    if not has_authority:
        return "rejected"   

    from concord.conditionals.client import ConditionalClient
    conditionalClient = ConditionalClient(actor="system")
    condition_template = conditionalClient.get_condition_template_for_owner(community.pk)

    return check_conditional(action, condition_template)

# TODO: there should be one permission per action with multiple actors within the permission
# but for now we allow multiple with one actor each
def specific_permission_pipeline(action, specific_permissions):

    # If actor does not match specific permission, reject
    from concord.permission_resources.client import PermissionResourceClient
    permissionClient = PermissionResourceClient(actor="system")

    matching_permission = None
    for permission in specific_permissions:
        if permissionClient.actor_matches_permission(action.actor, permission):
            matching_permission = permission
            break

    if not matching_permission:
        return "rejected"

    from concord.conditionals.client import ConditionalClient
    conditionalClient = ConditionalClient(actor="system")
    condition_template = conditionalClient.get_condition_template_for_permission(matching_permission.pk)

    return check_conditional(action, condition_template)


def governing_permission_pipeline(action):
    individual_result = shortcut_for_individual_ownership(action)
    if individual_result:
        return individual_result

    from concord.communities.client import CommunityClient
    communityClient = CommunityClient(actor="system") 
    community = communityClient.get_owner(action.target)
    has_authority = communityClient.has_governing_authority(community, action.actor)
    if not has_authority:
        return "rejected"

    from concord.conditionals.client import ConditionalClient
    conditionalClient = ConditionalClient(actor="system")
    condition_template = conditionalClient.get_condition_template_for_governor(community.pk)

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
    return "rejected"

