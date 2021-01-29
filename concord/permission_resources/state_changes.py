"""Get state changes for permissions resources."""

import logging

from django.core.exceptions import ObjectDoesNotExist

from concord.actions.state_changes import BaseStateChange
from concord.permission_resources.models import PermissionsItem
from concord.utils.text_utils import get_verb_given_permission_type
from concord.utils.lookups import get_state_change_object
from concord.actions.models import TemplateModel
from concord.permission_resources.utils import delete_permissions_on_target
from concord.utils import field_utils


logger = logging.getLogger(__name__)


################################
### Permission State Changes ###
################################


class AddPermissionStateChange(BaseStateChange):
    """State change to add a permission to something."""
    change_description = "Add permission"
    section = "Permissions"
    model_based_validation = (PermissionsItem, ["change_type", "anyone", "inverse"])

    change_type = field_utils.CharField(label="Type of action the permission covers", required=True)
    actors = field_utils.ActorListField(label="Actors who have this permission", null_value=list)
    roles = field_utils.RoleListField(label="Roles who have this permission", null_value=list)
    configuration = field_utils.DictField(label="Configuration of the permission", null_value=dict)
    anyone = field_utils.BooleanField(label="Everyone has the permission", null_value=False)
    inverse = field_utils.BooleanField(label="Do the inverse of this permission", null_value=False)

    def description_present_tense(self):
        config_str = f" (configuration: {str(self.configuration)})" if self.configuration else ""
        return f"add permission '{get_verb_given_permission_type(self.change_type)}" + config_str + "'"

    def description_past_tense(self):
        config_str = f" (configuration: {str(self.configuration)})" if self.configuration else ""
        return f"added permission '{get_verb_given_permission_type(self.change_type)}" + config_str + "'"

    def is_conditionally_foundational(self, action):
        """Some state changes are only foundational in certain conditions. Those state changes override this
        method to apply logic and determine whether a specific instance is foundational or not."""
        from concord.utils.lookups import get_state_change_object
        change_object = get_state_change_object(self.change_type)
        return action.change.is_foundational

    def validate(self, actor, target):
        """We need to check configuration of permission is valid. Also need to check that the given
        permission can be set on the target."""

        if not super().validate(actor=actor, target=target):
            return False

        permission = get_state_change_object(self.change_type)

        # check that target is a valid class for the permission to be set on
        if target.__class__ not in permission.get_settable_classes():
            settable_classes_str = ", ".join([str(option) for option in permission.get_settable_classes()])
            self.set_validation_error(f"This kind of permission cannot be set on target {target} of class "
                                      + f"{target.__class__}, must be {settable_classes_str}")
            return False

        # check configuration
        if hasattr(permission, "check_configuration") and self.configuration:
            is_valid, error_message = permission.check_configuration_is_valid(self.configuration)
            if not is_valid:
                self.set_validation_error(error_message)
                return False

        return True

    def implement(self, actor, target, **kwargs):

        permission = PermissionsItem()
        permission.set_fields(
            owner=target.get_owner(), permitted_object=target, anyone=self.anyone, change_type=self.change_type,
            inverse=self.inverse, actors=self.actors, roles=self.roles, configuration=self.configuration
        )
        permission.save()
        return permission


class RemovePermissionStateChange(BaseStateChange):
    """State change to remove a permission from something."""
    change_description = "Remove permission"
    section = "Permissions"
    preposition = "from"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    def description_present_tense(self):
        return "remove permission"

    def description_past_tense(self):
        return "removed permission"

    def implement(self, actor, target, **kwargs):
        try:
            delete_permissions_on_target(target)
            target.delete()
            return True
        except ObjectDoesNotExist as exception:
            logger.warning(exception)
            return False


class AddActorToPermissionStateChange(BaseStateChange):
    """State change to add an actor to a permission."""
    change_description = "Add actor to permission"
    preposition = "for"
    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    actor_to_add = field_utils.ActorField(label="Actor to add", required=True)

    def description_present_tense(self):
        return f"add actor {self.actor_to_add} to permission"

    def description_past_tense(self):
        return f"added actor {self.actor_to_add} to permission"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if not isinstance(self.actor_to_add, str):
            self.set_validation_error(message=f"Actor must be passed as string not {type(self.actor_to_add)}")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.actors.add_actors(actors=[self.actor_to_add])
        target.save()
        return target


class RemoveActorFromPermissionStateChange(BaseStateChange):
    """State change to remove an actor from a permission."""
    change_description = "Remove actor from permission"
    preposition = "for"
    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    actor_to_remove = field_utils.ActorField(label="Actor to remove", required=True)

    def description_present_tense(self):
        return f"remove actor {self.actor_to_remove} from permission"

    def description_past_tense(self):
        return f"removed actor {self.actor_to_remove} from permission"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if target.actors.actor_in_list(int(self.actor_to_remove)):
            self.set_validation_error(message=f"Actor {self.actor_to_remove} is not set as an actor on this " +
                                      "permission so they cannot be removed.")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.actors.remove_actors(actors=[self.actor_to_remove])
        target.save()
        return target


class AddRoleToPermissionStateChange(BaseStateChange):
    """State change to add a role to a permission."""

    change_description = "Add role to permission"
    preposition = "for"
    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    role_name = field_utils.RoleField(label="Role to add", required=True)

    def description_present_tense(self):
        return f"add role {self.role_name} to permission"

    def description_past_tense(self):
        return f"added role {self.role_name} to permission"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        community_owner = target.get_owner()
        if not community_owner.roles.is_role(self.role_name):
            self.set_validation_error(message=f"{self.role_name} is not a role and so can't be set on permission")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.add_role_to_permission(role=self.role_name)
        target.save()
        return target


class RemoveRoleFromPermissionStateChange(BaseStateChange):
    """State change to remove a role from a permission."""
    change_description = "Remove role from permission"
    preposition = "for"
    section = "Permissions"
    configurable_fields = ["role_name"]
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    role_name = field_utils.RoleField(label="Role to remove", required=True)

    @classmethod
    def get_uninstantiated_description(cls, **configuration_kwargs):
        """Takes in an arbitrary number of configuration kwargs and uses them to
        create a description.  Does not reference fields passed on init."""
        return f"remove role {configuration_kwargs.get('role_name', '')} from permission"

    def description_present_tense(self):
        return f"remove role {self.role_name} from permission"

    def description_past_tense(self):
        return f"removed role {self.role_name} from permission"

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "role_name" in configuration:
            if not isinstance(configuration["role_name"], str):
                return False, "Role name must be sent as string, not " + str(type(configuration["role_name"]))
        return True, ""

    def check_configuration(self, action, permission):
        """All configurations must pass for the configuration check to pass."""
        configuration = permission.get_configuration()
        if "role_name" in configuration:
            if self.role_name not in configuration["role_name"]:
                return False, f"Can't remove role {self.role_name} from permission, allowable fields are: " + \
                              f"{', '.join(configuration['role_name'])}"
        return True, None

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if not target.roles.role_name_in_list(self.role_name):
            self.set_validation_error(message=f"{self.role_name} isn't a role on this permission so can't be removed")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.remove_role_from_permission(role=self.role_name)
        target.save()
        return target


class ChangePermissionConfigurationStateChange(BaseStateChange):
    """State change to change the configuration of a permission."""
    change_description = "Change configuration of permission"
    preposition = "for"
    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    configurable_field_name = field_utils.CharField(label="Name of field to configure", required=True)
    configurable_field_value = field_utils.CharField(label="Value to configure field to", required=True)

    def description_present_tense(self):
        return f"change configuration field {self.configurable_field_name} to value " + \
               f"{self.configurable_field_value} on permission"

    def description_past_tense(self):
        return f"changed configuration field {self.configurable_field_name} to value " + \
               f"{self.configurable_field_value} on permission"

    def implement(self, actor, target, **kwargs):

        configuration = target.get_configuration()

        configuration[self.configurable_field_name] = self.configurable_field_value
        target.set_configuration(configuration)

        target.save()
        return target


class ChangeInverseStateChange(BaseStateChange):
    """State change to toggle the inverse field of a permission."""

    change_description = "Toggle permission's inverse field"
    preposition = "for"
    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    change_to = field_utils.BooleanField(label="Change inverse field of permission to", required=True)

    def description_present_tense(self):
        return f"change inverse field to value {self.change_to} on permission"

    def description_past_tense(self):
        return f"changed inverse field to value {self.change_to} on permission"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if not isinstance(self.change_to, bool):
            self.set_validation_error(message=f"'change_to' must be True or False, not {type(self.change_to)}")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.inverse = self.change_to
        target.save()
        return target


class EnableAnyoneStateChange(BaseStateChange):
    """State change to set a permission so anyone can take it."""
    change_description = "Give anyone permission"
    section = "Permissions"
    preposition = "for"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    def description_present_tense(self):
        return "give anyone permission"

    def description_past_tense(self):
        return "gave anyone permission"

    def implement(self, actor, target, **kwargs):
        target.anyone = True
        target.save()
        return target


class DisableAnyoneStateChange(BaseStateChange):
    """State change which takes a permission that has 'anyone' enabled, so anyone can take it, and disables
    it so only the roles and actors specified can take it.."""
    change_description = "Remove anyone from permission"
    section = "Permissions"
    preposition = "for"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    def description_present_tense(self):
        return "remove anyone from permission"

    def description_past_tense(self):
        return "removed anyone from permission"

    def implement(self, actor, target, **kwargs):
        target.anyone = False
        target.save()
        return target


##############################
### Template State Changes ###
##############################


class EditTemplateStateChange(BaseStateChange):
    """State change to edit a template."""
    change_description = "Edit Template"
    allowable_targets = [TemplateModel]
    settable_classes = ["all_models"]

    template_object_id = field_utils.IntegerField(label="ID of Template to edit", required=True)
    field_name = field_utils.CharField(label="Field to edit", required=True)
    new_field_data = field_utils.DictField(label="Data to edit", required=True)

    def description_present_tense(self):
        return f"edit template field {self.field_name} to {self.new_field_data}"

    def description_past_tense(self):
        return f"edited template field {self.field_name} to {self.new_field_data}"

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        result = target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        if result.__class__.__name__ == "ValidationError":
            self.set_validation_error(result.message)
            return False
        return True

    def implement(self, actor, target, **kwargs):

        target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        target.save()

        return target
