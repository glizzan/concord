"""Client for permissions"""

from typing import Tuple, List

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from concord.actions.client import BaseClient
from concord.permission_resources.models import PermissionsItem
from concord.utils.pipelines import mock_action_pipeline
from concord.utils.lookups import get_state_changes_settable_on_model


################################
### PermissionResourceClient ###
################################


class PermissionResourceClient(BaseClient):
    """Client for interacting with Permission resources.  Target is usually the PermissionedModel
    that we're setting permissions on, but is occasionally the PermissionedModel itself."""
    app_name = "permission_resources"

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

    def has_permission(self, client, method_name, params, exclude_conditional=True):
        """Checks results of running a given (mock) action through the permissions pipeline.  Note that this
        says nothing about whether the given action is valid, as the validate step is called separately."""
        params = params if params else {}
        client.set_mode_for_all(mode="mock")
        mock_action = client.get_method(method_name)(**params, skip_validation=True)
        return mock_action_pipeline(mock_action, exclude_conditional)

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

    def get_condition_data(self) -> dict:
        """Get condition data on the target."""
        return self.target.get_condition_data()

    def get_settable_permissions_for_model(self, model_class):
        """Given a model class (or, optionally, an instance of a model class), gets the state change objects
        which may be set on that model via a permission."""
        if hasattr(model_class, "pk") and isinstance(model_class.pk, int):
            model_class = model_class.__class__   # just in case we've been passed in an instance
        return get_state_changes_settable_on_model(model_class)

    def get_settable_permissions(self, return_format="tuples") -> List[Tuple[str, str]]:
        """Gets a list of permissions it is possible to set on the target, in various formats"""
        permissions = self.get_settable_permissions_for_model(self.target)
        if return_format == "tuples":
            return [(permission.get_change_type(), permission.description) for permission in permissions]
        elif return_format == "list_of_strings":
            return [permission.get_change_type() for permission in permissions]
        return permissions

    # State changes

    # Complex/multiple state changes

    def update_configuration(self, *, configuration_dict: dict, permission):
        """Given a dict with the new configuration for a permission, change individual fields
        as needed."""

        self.target = permission
        actions = []
        old_configuration = permission.get_configuration()

        for field_name, field_value in configuration_dict.items():

            if (field_name in old_configuration and old_configuration[field_name] != field_value) or \
                    (field_name not in old_configuration and field_value not in [None, '', []]):

                action, result = self.change_configuration_of_permission(
                    configurable_field_name=field_name, configurable_field_value=field_value)
                actions.append(action)

        return actions

    def update_roles_on_permission(self, *, role_data, permission):
        """Given a list of roles, updates the given permission to match those roles."""

        self.target = permission
        action_list = []

        old_roles = set(permission.get_roles())
        new_roles = set(role_data)
        roles_to_add = new_roles.difference(old_roles)
        roles_to_remove = old_roles.difference(new_roles)

        for role in roles_to_add:
            action, result = self.add_role_to_permission(role_name=role)
            action_list.append(action)

        for role in roles_to_remove:
            action, result = self.remove_role_from_permission(role_name=role)
            action_list.append(action)

        return action_list

    def update_actors_on_permission(self, *, actor_data, permission):
        """Given a list of actors, updates the given permission to match those actors."""

        self.target = permission

        action_list = []

        old_actors = set(permission.get_actors())
        new_actors = set(actor_data)
        actors_to_add = new_actors.difference(old_actors)
        actors_to_remove = old_actors.difference(new_actors)

        for actor in actors_to_add:
            action, result = self.add_actor_to_permission(actor=actor)
            action_list.append(action)

        for actor in actors_to_remove:
            action, result = self.remove_actor_from_permission(actor=actor)
            action_list.append(action)

        return action_list
