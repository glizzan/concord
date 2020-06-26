from typing import Tuple, Any, List

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from concord.actions.client import BaseClient, ActionClient

from concord.permission_resources.models import PermissionsItem
from concord.permission_resources import utils, models
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
        return PermissionsItem.objects.filter(permitted_object_content_type=content_type, 
            permitted_object_id=object.pk)

    def get_permissions_for_role(self, *, role_name):
        matching_permissions = []
        # TODO: we probably want a way to easily filter to only the group
        for permission in PermissionsItem.objects.all():
            if permission.has_role(role=role_name):
                matching_permissions.append(permission)
        return matching_permissions

    def permission_has_condition(self, permission: PermissionsItem) -> bool:
        # TODO: may need to distinguish between None value vs a an empty template field
        return permission.condition is not None

    def actor_satisfies_permission(self, *, actor, permission: PermissionsItem) -> bool:
        return permission.match_actor(actor)

    def get_permission_or_return_mock(self, permitted_object_id, 
        permitted_object_content_type, permission_change_type):
        permissions = PermissionsItem.objects.filter(
            permitted_object_content_type = permitted_object_content_type,
            permitted_object_id = permitted_object_id,
            change_type = permission_change_type)
        if permissions:
            return permissions.first()
        else:
            return utils.MockMetaPermission(
                permitted_object_id = permitted_object_id, 
                permitted_object_content_type = permitted_object_content_type,
                permission_change_type = permission_change_type)

    def get_all_permissions_in_db(self):
        """Gets all permissions in the DB.  We should swap this out with getting all permissions in a group
        plus all of its owned objects but for now, this is what we have."""
        return PermissionsItem.objects.all()

    # Read methods which require target to be set

    def get_all_permissions(self) -> PermissionsItem:
        content_type = ContentType.objects.get_for_model(self.target)
        return PermissionsItem.objects.filter(permitted_object_content_type=content_type, 
            permitted_object_id=self.target.pk)

    # FIXME: "specific" permissions is, ironically, a non-specific variable name
    def get_specific_permissions(self, *, change_type: str) -> PermissionsItem:
        # FIXME: Possibly remove this check and refactor the permissions forms to be have more sensibly
        # and not call this method if there's no valid target set.
        if type(self.target) == utils.MockMetaPermission:
            return []
        content_type = ContentType.objects.get_for_model(self.target)
        # FIXME: I'm assuming the target is the permitted object but maybe that's wrong?
        return PermissionsItem.objects.filter(permitted_object_content_type=content_type, 
            permitted_object_id=self.target.pk, change_type=change_type)

    def get_permissions_associated_with_role_for_target(self, *, role_name: str) -> List[PermissionsItem]:
        permissions = self.get_permissions_on_object(object=self.target)
        matching_permissions = []
        for permission in permissions:
            if permission.has_role(role=role_name):
                matching_permissions.append(permission)
        return matching_permissions

    def get_roles_associated_with_permission(self, *, permission_pk: int):
        permission = PermissionsItem.objects.filter(pk=permission_pk).first()
        return permission.roles.get_roles()

    def get_permissions_associated_with_actor(self, actor: int) -> List[PermissionsItem]:
        permissions = self.get_permissions_on_object(object=self.target)
        matching_permissions = []
        for permission in permissions:
            if permission.actors.actor_in_list(actor):
                matching_permissions.append(permission)
        return matching_permissions

    def get_condition_data(self, info="all") -> dict:       
        return self.target.get_condition_data(info)

    # FIXME: also need to update tests
    
    def get_settable_permissions_for_model(self, model_class):
        """Given a model class (or, optionally, an instance of a model class), gets the state change objects
        which may be set on that model via a permission."""
        from concord.actions.utils import get_state_change_objects_which_can_be_set_on_model
        if hasattr(model_class, "pk") and type(model_class.pk) == int:
            model_class = model_class.__class__   # just in case we've been passed in an instance
        app_name = model_class._meta.app_label 
        return get_state_change_objects_which_can_be_set_on_model(model_class, app_name)

    def get_settable_permissions(self, return_format="tuples") -> List[Tuple[str,str]]:
        """Gets a list of permissions it is possible to set on the target, in various formats"""
        permissions = self.get_settable_permissions_for_model(self.target)
        if return_format == "tuples":
            return utils.format_as_tuples(permissions)
        elif return_format == "list_of_strings":
            return utils.format_as_list_of_strings(permissions)
        return permissions

    # State changes

    def add_permission(self, *, permission_type: str, permission_actors: list = None, 
            permission_roles: list = None, permission_configuration: dict = None, anyone=False) -> Tuple[int, Any]:
        if not permission_actors and not permission_roles and anyone is not True:
            raise Exception("Either actor or roles must be supplied when creating a permission")  
        change = sc.AddPermissionStateChange(permission_type=permission_type, 
            permission_actors=permission_actors, permission_roles=permission_roles,
            permission_configuration=permission_configuration, anyone=anyone)
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

    def add_role_to_permission(self, *, role_name: str, permission_pk: int) -> Tuple[int, Any]:
        change = sc.AddRoleToPermissionStateChange(role_name=role_name, permission_pk=permission_pk)
        return self.create_and_take_action(change)
    
    def remove_role_from_permission(self, *, role_name: str, permission_pk: int) -> Tuple[int, Any]:
        change = sc.RemoveRoleFromPermissionStateChange(role_name=role_name, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def change_configuration_of_permission(self, *, configurable_field_name: str, 
        configurable_field_value: str, permission_pk: int) -> Tuple[int, Any]:
        # FIXME: we should be able to change multiple fields at once, and then we can remove
        # update_configuration - there should be a configurable_fields here so you can limit the 
        # permission to one field
        change = sc.ChangePermissionConfigurationStateChange(configurable_field_name=configurable_field_name,
            configurable_field_value=configurable_field_value, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def change_inverse_field_of_permission(self, *, change_to: bool, permission_pk=int) -> Tuple[int, Any]:
        change = sc.ChangeInverseStateChange(change_to=change_to, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def give_anyone_permission(self, permission_pk):
        change = sc.EnableAnyoneStateChange(permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def remove_anyone_from_permission(self, permission_pk):
        change = sc.DisableAnyoneStateChange(permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def add_condition_to_permission(self, *, permission_pk, condition_type, condition_data=None, permission_data=None):
        change = sc.AddPermissionConditionStateChange(permission_pk=permission_pk, condition_type=condition_type, 
            condition_data=condition_data, permission_data=permission_data)
        return self.create_and_take_action(change)

    def remove_condition_from_permission(self, permission_pk):
        change = sc.RemovePermissionConditionStateChange(permission_pk=permission_pk)
        return self.create_and_take_action(change)

    # Complex/multiple state changes

    def update_configuration(self, *, configuration_dict: dict, permission):
        """Given a dict with the new configuration for a permission, change individual fields 
        as needed."""

        actions = []      
        old_configuration = permission.get_configuration()

        for field_name, field_value in configuration_dict.items():

            if (field_name in old_configuration and old_configuration[field_name] != field_value) or \
                (field_name not in old_configuration and field_value not in [None, '', []]):
                action, result = self.change_configuration_of_permission(configurable_field_name=field_name,
                    configurable_field_value=field_value, permission_pk=permission.pk)
                actions.append(action)

        return actions

    def update_roles_on_permission(self, *, role_data, permission):
        """Given a list of roles, updates the given permission to match those roles."""
        
        action_list = []

        old_roles = set(permission.get_role_names())
        new_roles = set(role_data)
        roles_to_add = new_roles.difference(old_roles)
        roles_to_remove = old_roles.difference(new_roles)

        for role in roles_to_add:
            action_list.append(self.add_role_to_permission(role_name=role, permission_pk=permission.pk))
        
        for role in roles_to_remove:
            action_list.append(self.remove_role_from_permission(role_name=role, permission_pk=permission.pk))

        return action_list

    def update_actors_on_permission(self, *, actor_data, permission, return_type="action"):
        """Given a list of actors, updates the given permission to match those actors."""

        action_list = []

        old_actors = set(permission.get_actors())
        new_actors = set(actor_data)
        actors_to_add = new_actors.difference(old_actors)
        actors_to_remove = old_actors.difference(new_actors)

        for actor in actors_to_add:
            action_list.append(self.add_actor_to_permission(actor=actor, permission_pk=permission.pk))
        
        for actor in actors_to_remove:
            action_list.append(self.remove_actor_from_permission(actor=actor, permission_pk=permission.pk))

        return action_list

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

                old_roles = set(permission.roles.get_roles())
                new_roles = set(new_permissions[permission.change_type])
                roles_to_add = new_roles.difference(old_roles)
                roles_to_remove = old_roles.difference(new_roles)

                for role in roles_to_add:
                    action = self.add_role_to_permission(role_name=role, permission_pk=permission.pk)
                    actions.append(action)
                
                for role in roles_to_remove:
                    action = self.remove_role_from_permission(role_name=role, permission_pk=permission.pk)
                    actions.append(action)

                # delete permission from new_permissions dict, leaving only newly created permissions
                del(new_permissions[permission.change_type])
            
        # Iterate through remaining new_permissions, these should all be permissions to create
        for permission, role_list in new_permissions.items():
            action = self.add_permission(permission_type=permission, 
                    permission_roles=role_list)
            actions.append(action)

        return actions

