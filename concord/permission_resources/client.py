"""Client for permissions"""

from typing import Tuple, Any, List

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from concord.actions.client import BaseClient
from concord.permission_resources.models import PermissionsItem
from concord.permission_resources import state_changes as sc
from concord.actions.permissions import has_permission
from concord.actions.utils import get_state_changes_settable_on_model_and_parents


################################
### PermissionResourceClient ###
################################


class PermissionResourceClient(BaseClient):
    """The "target" of a PermissionResourceClient is always the resource or community on which
    the permission resource we're manipulating is set.  As with all Concord clients, a
    target must be set for all methods not  explicitly grouped as target-less methods."""

    # Target-less methods (don't require a target to be set ahead of time)

    def get_permission(self, *, pk: int) -> PermissionsItem:
        """Gets permissions item given pk."""
        return PermissionsItem.objects.get(pk=pk)

    def get_permissions_on_object(self, *, target_object: Model) -> PermissionsItem:
        """Given a target object, get all permissions set on it."""
        content_type = ContentType.objects.get_for_model(target_object)
        return PermissionsItem.objects.filter(permitted_object_content_type=content_type,
                                              permitted_object_id=target_object.pk)

    def get_permissions_for_role(self, *, role_name):
        """Given a role, get all permissions associated with it."""
        matching_permissions = []
        for permission in PermissionsItem.objects.all():
            if permission.has_role(role=role_name):
                matching_permissions.append(permission)
        return matching_permissions

    def actor_satisfies_permission(self, *, actor, permission: PermissionsItem) -> bool:
        """Returns True if given actor satisfies given permission."""
        return permission.match_actor(actor)

    def get_all_permissions_in_db(self):
        """Gets all permissions in the DB.  We should swap this out with getting all permissions in a group
        plus all of its owned objects but for now, this is what we have."""
        return PermissionsItem.objects.all()

    def has_permission(self, client, method_name, parameters, exclude_conditional=False):
        """Checks results of running a given (mock) action through the permissions pipeline.  Note that this
        says nothing about whether the given action is valid, as the validate step is called separately."""
        client.mode = "mock"
        mock_action = getattr(client, method_name)(**parameters)
        mock_action = has_permission(mock_action)
        mock_action.status = mock_action.resolution.generate_status()
        if mock_action.status == "approved":
            return True
        if not exclude_conditional and mock_action.status == "waiting":
            return True
        return False

    # Read methods which require target to be set

    def get_all_permissions(self) -> PermissionsItem:
        """Get all permissions on the client target."""
        content_type = ContentType.objects.get_for_model(self.target)
        return PermissionsItem.objects.filter(
            permitted_object_content_type=content_type, permitted_object_id=self.target.pk
        )

    def get_specific_permissions(self, *, change_type: str) -> PermissionsItem:
        """Get all permissions on the client target matching the given change_type."""
        content_type = ContentType.objects.get_for_model(self.target)
        return PermissionsItem.objects.filter(
            permitted_object_content_type=content_type, permitted_object_id=self.target.pk, change_type=change_type
        )

    def get_permissions_associated_with_role_for_target(self, *, role_name: str) -> List[PermissionsItem]:
        """Get any permissions on the target associated with the given role."""
        permissions = self.get_permissions_on_object(target_object=self.target)
        matching_permissions = []
        for permission in permissions:
            if permission.has_role(role=role_name):
                matching_permissions.append(permission)
        return matching_permissions

    def get_roles_associated_with_permission(self, *, permission_pk: int):
        """Given a permission, get all roles set on it."""
        permission = PermissionsItem.objects.filter(pk=permission_pk).first()
        return permission.roles.get_roles()

    def get_permissions_associated_with_actor(self, actor: int) -> List[PermissionsItem]:
        """Given an actor, get all permissions on the target they are listed as an individual actor within."""
        permissions = self.get_permissions_on_object(target_object=self.target)
        matching_permissions = []
        for permission in permissions:
            if permission.actors.actor_in_list(actor):
                matching_permissions.append(permission)
        return matching_permissions

    def get_condition_data(self, info="all") -> dict:
        """Get condition data on the target."""
        return self.target.get_condition_data(info)

    def get_settable_permissions_for_model(self, model_class):
        """Given a model class (or, optionally, an instance of a model class), gets the state change objects
        which may be set on that model via a permission."""
        if hasattr(model_class, "pk") and isinstance(model_class.pk, int):
            model_class = model_class.__class__   # just in case we've been passed in an instance
        return get_state_changes_settable_on_model_and_parents(model_class)

    def get_settable_permissions(self, return_format="tuples") -> List[Tuple[str, str]]:
        """Gets a list of permissions it is possible to set on the target, in various formats"""
        permissions = self.get_settable_permissions_for_model(self.target)
        if return_format == "tuples":
            return [(permission.get_change_type(), permission.description) for permission in permissions]
        elif return_format == "list_of_strings":
            return [permission.get_change_type() for permission in permissions]
        return permissions

    # State changes

    def add_permission(self, *, permission_type: str, permission_actors: list = None, permission_roles: list = None,
                       permission_configuration: dict = None, anyone=False) -> Tuple[int, Any]:
        """Add permission to target."""
        if not permission_actors and not permission_roles and anyone is not True:
            raise Exception("Either actor or roles must be supplied when creating a permission")
        change = sc.AddPermissionStateChange(
            permission_type=permission_type, permission_actors=permission_actors, permission_roles=permission_roles,
            permission_configuration=permission_configuration, anyone=anyone
        )
        return self.create_and_take_action(change)

    def remove_permission(self, *, item_pk: int) -> Tuple[int, Any]:
        """Remove permission from target."""
        change = sc.RemovePermissionStateChange(item_pk=item_pk)
        return self.create_and_take_action(change)

    def add_actor_to_permission(self, *, actor: str, permission_pk: int) -> Tuple[int, Any]:
        """Add actor to permission."""
        change = sc.AddActorToPermissionStateChange(actor_to_add=actor, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def remove_actor_from_permission(self, *, actor: str, permission_pk: int) -> Tuple[int, Any]:
        """Remove actor from permission."""
        change = sc.RemoveActorFromPermissionStateChange(actor_to_remove=actor, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def add_role_to_permission(self, *, role_name: str, permission_pk: int) -> Tuple[int, Any]:
        """Add role to permission."""
        change = sc.AddRoleToPermissionStateChange(role_name=role_name, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def remove_role_from_permission(self, *, role_name: str, permission_pk: int) -> Tuple[int, Any]:
        """Remove role from permission."""
        change = sc.RemoveRoleFromPermissionStateChange(role_name=role_name, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def change_configuration_of_permission(self, *, configurable_field_name: str, configurable_field_value: str,
                                           permission_pk: int) -> Tuple[int, Any]:
        """Change the configuration of the permission."""
        change = sc.ChangePermissionConfigurationStateChange(
            configurable_field_name=configurable_field_name, configurable_field_value=configurable_field_value,
            permission_pk=permission_pk
        )
        return self.create_and_take_action(change)

    def change_inverse_field_of_permission(self, *, change_to: bool, permission_pk=int) -> Tuple[int, Any]:
        """Toggle the inverse field on the permission."""
        change = sc.ChangeInverseStateChange(change_to=change_to, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def give_anyone_permission(self, permission_pk):
        """Make it so everyone has the permission."""
        change = sc.EnableAnyoneStateChange(permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def remove_anyone_from_permission(self, permission_pk):
        """Remove the ability for everyone to have the permission."""
        change = sc.DisableAnyoneStateChange(permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def add_condition_to_permission(self, *, permission_pk, condition_type, condition_data=None, permission_data=None):
        """Add a condition to the permission."""
        change = sc.AddPermissionConditionStateChange(
            permission_pk=permission_pk, condition_type=condition_type, condition_data=condition_data,
            permission_data=permission_data
        )
        return self.create_and_take_action(change)

    def remove_condition_from_permission(self, permission_pk):
        """Remove a condition from the permission."""
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
                action, result = self.change_configuration_of_permission(
                    configurable_field_name=field_name, configurable_field_value=field_value,
                    permission_pk=permission.pk
                )
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

    def update_actors_on_permission(self, *, actor_data, permission):
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
