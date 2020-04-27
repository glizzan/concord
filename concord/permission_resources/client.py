from typing import Tuple, Any, List

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from concord.actions.client import BaseClient

from concord.permission_resources.models import PermissionsItem
from concord.permission_resources import utils, templates, models
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
            permission_roles: list = None, permission_configuration: dict = None) -> Tuple[int, Any]:
        if not permission_actors and not permission_roles:
            raise Exception("Either actor or role_pair must be supplied when creating a permission")
        change = sc.AddPermissionStateChange(permission_type=permission_type, 
            permission_actors=permission_actors, permission_roles=permission_roles,
            permission_configuration=permission_configuration)
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
        change = sc.ChangePermissionConfigurationStateChange(configurable_field_name=configurable_field_name,
            configurable_field_value=configurable_field_value, permission_pk=permission_pk)
        return self.create_and_take_action(change)

    def change_inverse_field_of_permission(self, *, change_to: bool, permission_pk=int) -> Tuple[int, Any]:
        change = sc.ChangeInverseStateChange(change_to=change_to, permission_pk=permission_pk)
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

    def update_roles_on_permission(self, *, role_data, permission, owner):
        """Given a list of roles, updates the given permission to match those roles."""
        
        actions = []

        old_roles = set(permission.get_role_names())
        new_roles = set(role_data)
        roles_to_add = new_roles.difference(old_roles)
        roles_to_remove = old_roles.difference(new_roles)

        for role in roles_to_add:
            action = self.add_role_to_permission(role_name=role, permission_pk=permission.pk)
            actions.append(action)
        
        for role in roles_to_remove:
            action = self.remove_role_from_permission(role_name=role, permission_pk=permission.pk)
            actions.append(action)

        # FIXME: why is this here??????
        permission = PermissionsItem.objects.get(pk=permission.pk)

        return actions

    def update_actors_on_permission(self, *, actor_data, permission):
        """Given a list of roles, updates the given permission to match those roles."""

        actions = []

        old_actors = set(permission.get_actors())
        new_actors = set(actor_data)
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


######################
### TemplateClient ###
######################


class TemplateClient(BaseClient):

    # Get data, no target assumed

    def get_template_given_id(self, *, template_id):
        return models.Template.objects.get(pk=template_id)

    def get_editable_fields_on_template(self, template_id=None, template_model=None):
        if not template_id and not template_model:
            raise Exception("Must provide either template model or template_id.")
        if template_id:
            template_model = self.get_template_given_id()
        return template_model.data.get_editable_fields()

    # Creates

    def make_template(self, *, description=None, community=None, permissions=None, conditions=None, 
        owned_objects=None, recursive=False):
        template_model = models.Template(description=description, owner=self.actor.default_community)
        template_model.data.create_template(community=community, permissions=permissions, 
            conditions=conditions, owned_objects=owned_objects, recursive=recursive)
        template_model.save()

        # HACK: is there a better way to "refresh" the model so it's no longer attached to the original
        # django models?
        template_model = self.get_template_given_id(template_id=template_model.pk)
        return template_model 

    def create_from_template(self, *, template_model=None, template_id=None, default_owner=None):
        if not template_model and not template_id and not self.target:
            raise Exception("Must provide either template_model or template_id to create_from_template.")
        if template_id:
            template_model = self.get_template_given_id(template_id=template_id)
        if not template_id and not template_model:
            template_model= self.target
        default_owner = default_owner if default_owner else self.actor
        return template_model.data.create_from_template(default_owner=default_owner)

    # State changes

    def edit_template_field(self, *, template_object_id, field_name, new_field_data):
        change = sc.EditTemplateStateChange(template_object_id=template_object_id, 
            field_name=field_name, new_field_data=new_field_data)
        return self.create_and_take_action(change)

    # Helper/complex methods

    def update_field_and_get_new_data(self, *, template_object_id, field_name, new_field_data):
        action, result = self.edit_template_field(template_object_id=template_object_id, 
            field_name=field_name, new_field_data=new_field_data)
        if action.resolution.status == "rejected":
            return action
        else:
            self.refresh_target()
            return { 
                "template_text": self.target.data.generate_text(),
                "editable_fields": self.get_editable_fields_on_template(template_model=self.target)
                }
