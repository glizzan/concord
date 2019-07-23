from typing import Tuple, Any, List

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from concord.actions.client import BaseClient

from concord.permission_resources.models import PermissionsItem
from concord.permission_resources import utils
from concord.permission_resources import state_changes as sc


################################
### PermissionResourceClient ###
################################

# NOTE: I *believe* the target of a PRC should be the target associated with the PR, but
# need to verify and then document.

class PermissionResourceClient(BaseClient):
    """
    The "target" of a PermissionResourceClient is always the resource or community on which
    the permission resource we're manipulating is set.  As with all Concord clients, a 
    target must be set for all methods not  explicitly grouped as target-less methods.
    """

    # Target-less methods (don't require a target to be set ahead of time)

    def get_permission(self, *, pk: int) -> PermissionsItem:
        return PermissionsItem.objects.get(pk=pk)

    def get_permissions_on_object(self, *, object: Model) -> PermissionsItem:
        content_type = ContentType.objects.get_for_model(object)
        return PermissionsItem.objects.filter(content_type=content_type, object_id=object.pk)

    def actor_matches_permission(self, *, actor: str, permission: PermissionsItem) -> bool:
        return permission.match_actor(actor)  # Returns boolean & role if it exists

    def get_permission_or_return_mock(self, permitted_object_pk, 
        permitted_object_ct, permission_change_type):
        permissions = PermissionsItem.objects.filter(
            content_type = permitted_object_ct,
            object_id = permitted_object_pk,
            change_type = permission_change_type)
        if permissions:
            return permissions.first()
        else:
            return utils.MockMetaPermission(
                permitted_object_pk = permitted_object_pk, 
                permitted_object_ct = permitted_object_ct,
                permission_change_type = permission_change_type)

    # Read methods which require target to be set

    def get_all_permissions(self) -> PermissionsItem:
        content_type = ContentType.objects.get_for_model(self.target)
        return PermissionsItem.objects.filter(content_type=content_type, object_id=self.target.pk)

    def get_specific_permissions(self, *, change_type: str) -> PermissionsItem:
        content_type = ContentType.objects.get_for_model(self.target)
        return PermissionsItem.objects.filter(content_type=content_type, object_id=self.target.pk, 
            change_type=change_type)

    def get_permissions_associated_with_role(self, *, role_name: str, community: Model) -> List[PermissionsItem]:
        permissions = self.get_permissions_on_object(object=self.target)
        role_pair = str(community.pk) + "_" + role_name
        matching_permissions = []
        for permission in permissions:
            if role_pair in permission.get_roles():
                matching_permissions.append(permission)
        return matching_permissions

    def get_roles_associated_with_permission(self, *, permission_pk: int):
        permission = PermissionsItem.objects.filter(pk=permission_pk).first()
        return permission.get_roles()

    def get_permissions_associated_with_actor(self, actor: str) -> List[PermissionsItem]:
        permissions = self.get_permissions_on_object(object=self.target)
        matching_permissions = []
        for permission in permissions:
            if actor in permission.get_actors():
                matching_permissions.append(permission)
        return matching_permissions

    def get_settable_permissions(self, return_format="tuples") -> List[Tuple[str,str]]:
        """Gets a list of permissions it is possible to set on the target, return type copied from
        target.get_settable_permissions() return type."""
        # NOTE: doesn't actually require target if given a class
        permissions = utils.get_settable_permissions(target=self.target)
        if return_format == "tuples":
            return utils.format_as_tuples(permissions)
        elif return_format == "list_of_strings":
            return utils.format_as_list_of_strings(permissions)
        return permissions

    def get_settable_permissions_for_user(self, *, name):
        ...

    # State changes

    def add_permission(self, *, permission_type: str, permission_actors: list = None, 
            permission_role_pairs: list = None) -> Tuple[int, Any]:
        if not permission_actors and not permission_role_pairs:
            raise Exception("Either actor or role_pair must be supplied when creating a permission")
        change = sc.AddPermissionStateChange(permission_type=permission_type, 
            permission_actors=permission_actors, permission_role_pairs=permission_role_pairs)
        return self.create_and_take_action(change)

    def remove_permission(self, *, item_pk: int) -> Tuple[int, Any]:
        change = sc.RemovePermissionStateChange(item_pk=item_pk)
        return self.create_and_take_action(change)

    def add_actor_to_permission(self, *, actor: str, permission_pk: int) -> Tuple[int, Any]:
        change = sc.AddActorToPermissionStateChange(actor_to_add=actor, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def remove_actor_from_permission(self, *, actor: str, permission_pk: int) -> Tuple[int, Any]:
        change = sc.RemoveActorFromPermissionStateChange(actor_to_remove=actor, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def add_role_to_permission(self, *, role_name: str, community_pk: int, permission_pk: int) -> Tuple[int, Any]:
        change = sc.AddRoleToPermissionStateChange(role_name=role_name, permission_pk=permission_pk,
            community_pk=community_pk)
        return self.create_and_take_action(change)
    
    def remove_role_from_permission(self, *, role_name: str, community_pk: int, permission_pk: int) -> Tuple[int, Any]:
        change = sc.RemoveRoleFromPermissionStateChange(role_name=role_name, permission_pk=permission_pk,
            community_pk=community_pk)
        return self.create_and_take_action(change)

    # Complex/multiple state changes

    def update_roles_on_permission(self, *, role_data, permission, owner):
        """Given a list of roles, updates the given permission to match those roles."""

        actions = []

        old_roles = set(permission.get_role_names())
        new_roles = set(role_data)
        roles_to_add = new_roles.difference(old_roles)
        roles_to_remove = old_roles.difference(new_roles)

        for role in roles_to_add:
            action = self.add_role_to_permission(role_name=role, 
                community_pk=owner.pk, permission_pk=permission.pk)
            actions.append(action)
        
        for role in roles_to_remove:
            action = self.remove_role_from_permission(role_name=role, 
                community_pk=owner.pk, permission_pk=permission.pk)
            actions.append(action)

        permission = PermissionsItem.objects.get(pk=permission.pk)

        return actions

    def update_actors_on_permission(self, *, actor_data, permission):
        """Given a list of roles, updates the given permission to match those roles."""

        actions = []

        old_actors = set(permission.get_actors())
        new_actors = set(actor_data.split(" "))
        actors_to_add = new_actors.difference(old_actors)
        actors_to_remove = old_actors.difference(new_actors)

        for actor in actors_to_add:
            action = self.add_actor_to_permission(actor=actor, 
                permission_pk=permission.pk)
            actions.append(action)
        
        for actor in actors_to_remove:
            action = self.remove_actor_from_permission(actor=actor, 
                permission_pk=permission.pk)
            actions.append(action)

        return actions


    # FIXME: this is still too complex
    def update_role_permissions(self, *, role_data, owner):
        """Given a dict with roles and permissions on a target object which refer 
        to those roles, goes through permissions on target object and adds or removes
        references to roles to make them match the given dict."""
        
        actions = []

        # Reformulate role_data with permissions as key for readability/usability
        new_permissions = {}
        for index, role in role_data.items():
            for permission in role["permissions"]:
                if permission not in new_permissions:
                    new_permissions[permission] = [role["rolename"]]
                else:
                    new_permissions[permission].append(role["rolename"])

        # Iterate through old_permissions.  
        old_permissions = self.get_permissions_on_object(object=self.target)
        for permission in old_permissions:

            if permission.change_type not in new_permissions:

                # If not in new_permissions, delete.
                action = self.remove_permission(item_pk=permission.pk)
                actions.append(action)

            else:

                # Otherwise, update role data.

                old_roles = set(permission.get_roles())
                new_roles = set(new_permissions[permission.change_type])
                roles_to_add = new_roles.difference(old_roles)
                roles_to_remove = old_roles.difference(new_roles)

                for role in roles_to_add:
                    action = self.add_role_to_permission(role_name=role, 
                        community_pk=owner.pk, permission_pk=permission.pk)
                    actions.append(action)
                
                for role in roles_to_remove:
                    action = self.remove_role_from_permission(role_name=role, 
                        community_pk=owner.pk, permission_pk=permission.pk)
                    actions.append(action)

                # delete permission from new_permissions dict, leaving only newly created permissions
                del(new_permissions[permission.change_type])
            
        # Iterate through remaining new_permissions, these should all be permissions to create
        for permission, role_list in new_permissions.items():
            for role_name in role_list:
                role_pair = str(owner.pk) + "_" + role_name
                action = self.add_permission(permission_type=permission, 
                    permission_role_pairs=[role_pair])
                actions.append(action)

        return actions