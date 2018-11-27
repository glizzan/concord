def check_condition(action, permission):
    from conditionals.client import ConditionalClient

    # Does the permission have a condition?  If no, just approve it.
    cc = ConditionalClient(actor=action.actor) 
    condition_template = cc.get_condition_template_given_permission(permission_pk=permission.pk)
    if not condition_template:
        return "approved"

    # If it does have a condition, does this action already have a condition action
    # instance?  If no, make one.
    condition_item = cc.get_or_create_condition_item(condition_template=condition_template,
        action=action)

    return condition_item.condition_status()

def get_permissions_resource(action):
    from permission_resources.client import PermissionResourceClient
    prc = PermissionResourceClient(actor=action.actor)
    return prc.get_permission_resource(permitted_object=action.target)

def check_individual_default_permission(action):
    """For individuals, the default permission is that the owner
    can do anything and everyone else can do nothing."""
    if action.actor == action.target.get_owner():
        return "approved"
    return "rejected"

def check_community_default_permission(action):
    """
    Checks whether the actor is authorized by the default permission by
    checking the target owner's authority handler.
    """
    from communities.client import CommunityClient
    cc = CommunityClient(actor="view_only")
    return cc.does_actor_have_default_permission_on_community(action)

def check_default_permission(action, resource):
    '''For now, the default permission is the owner can do everything and no
    one else can do anything.  Use it unless explicitly overridden.'''
    if resource and resource.ignore_defaults:
        return "rejected"
    if action.target.owner_type == "ind":
        return check_individual_default_permission(action)
    elif action.target.owner_type == "com":
        return check_community_default_permission(action)
    return "rejected"

def get_applicable_permissions(action):
    applicable_permissions = []
    resource = get_permissions_resource(action)
    if resource:
        for permission in resource.permissionsitem_set.all():  # Needs to be through client
            if permission.match_action_type(action.change_type):
                applicable_permissions.append(permission)
    return resource, applicable_permissions

def has_permission(action):

    resource, applicable_permissions = get_applicable_permissions(action)

    # For each permission, look for matching actor and return result of first match.
    for permission in applicable_permissions:
        if permission.match_actor(action.actor):
            return check_condition(action, permission)

    # If we didn't match a permission above (perhaps because there aren't any!) check
    # the default permission (basically, see if actor is owner) and return result.
    return check_default_permission(action, resource)
