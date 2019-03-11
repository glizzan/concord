from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist

from concord.actions.clients import BaseActionClient

from concord.permission_resources.models import PermissionsItem
from concord.permission_resources import state_changes as sc


################################
### PermissionResourceClient ###
################################


class PermissionResourceClient(BaseActionClient):

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

    def actor_matches_permission(self, actor, permission):
        # TODO: if we do another lookup using permission pk, this causes another lookup
        # but if we don't, then it's kinda entangled.
        if permission.match_actor(actor):
            return True
        return False

    # State changes

    def add_permission(self, permission_type, permission_actor=None, permission_role=None, target=None):
        if not permission_actor and not permission_role:
            raise("Either actor or role must be specified when creating a permission")
        change = sc.AddPermissionStateChange(permission_type=permission_type, 
            permission_actor=permission_actor, permission_role=permission_role)
        return self.create_and_take_action(change, target)

    def remove_permission(self, item_pk, target=None):
        change = sc.RemovePermissionStateChange(item_pk=item_pk)
        return self.create_and_take_action(change, target)

    def add_actor_to_permission(self, actor_to_be_added, target=None):
        change = sc.AddActorToPermissionStateChange(actor_to_be_added=actor_to_be_added)
        return self.create_and_take_action(change, target)

    def remove_actor_from_permission(self, actor_to_be_removed, target=None):
        change = sc.RemoveActorFromPermissionStateChange(actor_to_be_removed=actor_to_be_removed)
        return self.create_and_take_action(change, target)

    def add_role_to_permission(self, role_name, community_pk, target=None):
        change = sc.AddRoleToPermissionStateChange(role_name=role_name, community_pk=community_pk)
        return self.create_and_take_action(change, target)
    
    def remove_role_from_permission(self, role_name, community_pk, target=None):
        change = sc.RemoveRoleFromPermissionStateChange(role_name=role_name, community_pk=community_pk)
        return self.create_and_take_action(change, target)

