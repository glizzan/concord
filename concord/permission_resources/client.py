from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist

from concord.actions.clients import BaseActionClient

from concord.permission_resources.models import PermissionsItem
from concord.permission_resources import state_changes as sc


################################
### PermissionResourceClient ###
################################

# NOTE: I *believe* the target of a PRC should be the target associated with the PR, but
# need to verify and then document.

class PermissionResourceClient(BaseActionClient):
    """
    The "target" of a PermissionResourceClient is always the resource or community on which
    the permission resource we're manipulating is set.
    """

    # Read only
    def get_all_permissions_on_object(self, target):
        content_type = ContentType.objects.get_for_model(target)
        return PermissionsItem.objects.filter(content_type=content_type, object_id=target.pk)

    def get_specific_permissions(self, target, change_type):
        try:
            content_type = ContentType.objects.get_for_model(target)
            return PermissionsItem.objects.filter(content_type=content_type, object_id=target.pk, 
                change_type=change_type)
        except ObjectDoesNotExist:
            return None

    def get_permissions_associated_with_role(self, target, role_name, community):
        permissions = self.get_all_permissions_on_object(target=target)
        role_pair = str(community.pk) + "_" + role_name
        matching_permissions = []
        for permission in permissions:
            if role_pair in permission.get_roles():
                matching_permissions.append(permission)
        return matching_permissions

    def get_settable_permissions(self, target):
        """Gets a list of permissions it is possible to set on the target."""
        # TODO: create a version of this which checks what permissions the user can set.
        return target.get_settable_permissions()

    def actor_matches_permission(self, actor, permission):
        # TODO: if we do another lookup using permission pk, this causes another lookup
        # but if we don't, then it's kinda entangled.
        if permission.match_actor(actor):
            return True
        return False

    # State changes

    def add_permission(self, permission_type, permission_actor=None, permission_role=None, target=None):
        # FIXME: it's not clear here that 'permission_role' needs to be a role PAIR not name
        if not permission_actor and not permission_role:
            raise("Either actor or role must be specified when creating a permission")
        change = sc.AddPermissionStateChange(permission_type=permission_type, 
            permission_actor=permission_actor, permission_role=permission_role)
        return self.create_and_take_action(change, target)

    def remove_permission(self, item_pk, target=None):
        change = sc.RemovePermissionStateChange(item_pk=item_pk)
        return self.create_and_take_action(change, target)

    def add_actor_to_permission(self, actor, permission, target=None):
        change = sc.AddActorToPermissionStateChange(actor=actor, permission=permission)
        return self.create_and_take_action(change, target)

    def remove_actor_from_permission(self, actor, permission, target=None):
        change = sc.RemoveActorFromPermissionStateChange(actor=actor, permission=permission)
        return self.create_and_take_action(change, target)

    def add_role_to_permission(self, role_name, community_pk, permission, target=None):
        change = sc.AddRoleToPermissionStateChange(role_name=role_name, 
            community_pk=community_pk, permission=permission)
        return self.create_and_take_action(change, target)
    
    def remove_role_from_permission(self, role_name, community_pk, permission, target=None):
        change = sc.RemoveRoleFromPermissionStateChange(role_name=role_name, 
            community_pk=community_pk, permission=permission)
        return self.create_and_take_action(change, target)

