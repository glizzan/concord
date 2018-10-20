'''
The permissions system works recurisvely.

First, we check if a permissions resource has been created at all.  If not, we use
the default permissions.  If yes, we check the permissions system.
'''

def get_permissions_resource(action):
    from permission_resources.client import PermissionResourceClient
    prc = PermissionResourceClient(actor=action.actor)
    return prc.get_permission_resource(permitted_object=action.target)

def check_permission(resource, action):
    for permission in resource.permissionsitem_set.all():  # Needs to be through client
        if permission.match_action_type(action.change_type):
            return permission.match_actor(action.actor)
    # If we get here, there's no permission set for this type
    if resource.ignore_defaults:
        # If we're ignoring defaults, that means no permission is set, so return False
        return False
    # Otherwise, check if the actor matches the default permission
    return check_default_permission(action)

def check_default_permission(action):
    '''For now, the default permission is the creator can do everything and no
    one else can do anything.'''
    if action.target.get_creator() == action.actor:
        return True
    return False

def has_permission(action):
    resource = get_permissions_resource(action)
    if resource:
        return check_permission(resource, action)
    else:
        return check_default_permission(action)
