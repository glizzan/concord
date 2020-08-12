"""Get state changes for permissions resources."""

import logging

from django.core.exceptions import ValidationError, ObjectDoesNotExist

from concord.actions.state_changes import BaseStateChange
from concord.permission_resources.models import PermissionsItem
from concord.actions.text_utils import condition_template_to_text, get_verb_given_permission_type
from concord.resources.models import Resource, Item
from concord.actions.utils import get_state_change_object
from concord.actions.utils import Client
from concord.permission_resources.models import Template


logger = logging.getLogger(__name__)


################################
### Permission State Changes ###
################################


class PermissionResourceBaseStateChange(BaseStateChange):
    """Base state change containing some helper methods that permission resource state changes inherit from."""
    instantiated_fields = ['permission']

    def look_up_permission(self):
        """Given a permission_pk, looks up the existing permission in the db."""
        if hasattr(self, "permission") and self.permission.pk == self.permission_pk:
            return self.permission
        return PermissionsItem.objects.get(pk=self.permission_pk)

    def instantiate_fields(self):
        """Instantiates all fields on the state change."""
        self.permission = self.look_up_permission()


class AddPermissionStateChange(PermissionResourceBaseStateChange):
    """State change to add a permission to something."""
    description = "Add permission"

    def __init__(self, permission_type, permission_actors, permission_roles,
                 permission_configuration, anyone=False, inverse=False):
        """Permission actors and permission role pairs MUST be a list of zero or more
        strings."""
        self.permission_type = permission_type
        self.permission_actors = permission_actors if permission_actors else []
        self.permission_roles = permission_roles if permission_roles else []
        self.permission_configuration = permission_configuration
        self.inverse = inverse
        self.anyone = anyone

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        config_str = f" (configuration: {str(self.permission_configuration)})" if self.permission_configuration else ""
        return f"add permission {get_verb_given_permission_type(self.permission_type)}" + config_str

    def description_past_tense(self):
        config_str = f" (configuration: {str(self.permission_configuration)})" if self.permission_configuration else ""
        return f"added permission {get_verb_given_permission_type(self.permission_type)}" + config_str

    def validate(self, actor, target):
        """ To validate a permission being added, we need to instantiate the permission and check its configuration
        is valid. We also need to validate that the given permission can be set on the target."""
        permission = get_state_change_object(self.permission_type)

        # check that target is a valid class for the permission to be set on
        if target.__class__ not in permission.get_settable_classes():
            settable_classes_str = ", ".join([str(option) for option in permission.get_settable_classes()])
            self.set_validation_error(f"This kind of permission cannot be set on target {target} of class " +
                                      f"{target.__class__}, must be {settable_classes_str}")
            return False

        # check configuration
        if hasattr(permission, "check_configuration") and self.permission_configuration is not None:
            is_valid, error_message = permission.check_configuration_is_valid(self.permission_configuration)
            if not is_valid:
                self.set_validation_error(error_message)
                return False

        return True

    def implement(self, actor, target):

        permission = PermissionsItem()
        permission.set_fields(
            owner=target.get_owner(),
            permitted_object=target,
            anyone=self.anyone,
            change_type=self.permission_type,
            inverse=self.inverse,
            actors=self.permission_actors,
            roles=self.permission_roles,
            configuration=self.permission_configuration
        )
        permission.save()
        return permission


class RemovePermissionStateChange(PermissionResourceBaseStateChange):
    """State change to remove a permission from something."""
    description = "Remove permission"
    preposition = "from"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        return f"remove permission with id {self.item_pk}"

    def description_past_tense(self):
        return f"removed permission with id {self.item_pk}"

    def validate(self, actor, target):
        """
        put real logic here
        """
        if actor and target and self.item_pk:
            return True
        self.set_validation_error("Must supply item_pk")
        return False

    def implement(self, actor, target):
        try:
            item = PermissionsItem.objects.get(pk=self.item_pk)
            item.delete()
            return True
        except ObjectDoesNotExist as exception:
            logger.warning(exception)
            return False


class AddActorToPermissionStateChange(PermissionResourceBaseStateChange):
    """State change to add an actor to a permission."""

    description = "Add actor to permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, actor_to_add: str, permission_pk: int):
        self.actor_to_add = actor_to_add
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"add actor {self.actor_to_add} to permission {self.permission_pk}" + permission_str

    def description_past_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"added actor {self.actor_to_add} to permission {self.permission_pk}" + permission_str

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.actors.add_actors(actors=[self.actor_to_add])
        self.permission.save()
        return self.permission


class RemoveActorFromPermissionStateChange(PermissionResourceBaseStateChange):
    """State change to remove an actor from a permission."""
    description = "Remove actor from permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, actor_to_remove: str, permission_pk: int):
        self.actor_to_remove = actor_to_remove
        self.permission_pk = permission_pk
        self.permission = self.look_up_permission()

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"remove actor {self.actor_to_remove} from permission {self.permission_pk}" + permission_str

    def description_past_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"removed actor {self.actor_to_remove} from permission {self.permission_pk}" + permission_str

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.actors.remove_actors(actors=[self.actor_to_remove])
        self.permission.save()
        return self.permission


class AddRoleToPermissionStateChange(PermissionResourceBaseStateChange):
    """State change to add a role to a permission."""

    description = "Add role to permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, role_name: str, permission_pk: int):
        self.role_name = role_name
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"add role {self.role_name} to permission {self.permission_pk}" + permission_str

    def description_past_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"added role {self.role_name} to permission {self.permission_pk}" + permission_str

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.add_role_to_permission(role=self.role_name)
        self.permission.save()
        return self.permission


class RemoveRoleFromPermissionStateChange(PermissionResourceBaseStateChange):
    """State change to remove a role from a permission."""

    description = "Remove role from permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, role_name: str, permission_pk: int):
        self.role_name = role_name
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    @classmethod
    def get_configurable_fields(cls):
        return {"role_name": {
            "display": "Role that can be removed from the permission", "type": "PermissionRoleField"}}

    @classmethod
    def get_uninstantiated_description(cls, **configuration_kwargs):
        """Takes in an arbitrary number of configuration kwargs and uses them to
        create a description.  Does not reference fields passed on init."""
        return f"remove role {configuration_kwargs.get('role_name', '')} from permission"

    def description_present_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"remove role {self.role_name} from permission {self.permission_pk}" + permission_str

    def description_past_tense(self):
        permission_str = f" ({self.permission.get_change_type()})" if hasattr(self, "permission") else ""
        return f"removed role {self.role_name} from permission {self.permission_pk}" + permission_str

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
        self.instantiate_fields()
        configuration = permission.get_configuration()
        if "role_name" in configuration:
            if self.role_name not in configuration["role_name"]:
                return False, f"Can't remove role {self.role_name} from permission, allowable fields are: " + \
                              f"{', '.join(configuration['role_name'])}"
        return True, None

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.remove_role_from_permission(role=self.role_name)
        self.permission.save()
        return self.permission


class ChangePermissionConfigurationStateChange(PermissionResourceBaseStateChange):
    """State change to change the configuration of a permission."""

    description = "Change configuration of permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, configurable_field_name: str, configurable_field_value: str, permission_pk: int):
        self.configurable_field_name = configurable_field_name
        self.configurable_field_value = configurable_field_value
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        return f"change configuration field {self.configurable_field_name} to value " + \
               f"{self.configurable_field_value} on permission {self.permission_pk}"

    def description_past_tense(self):
        return f"changed configuration field {self.configurable_field_name} to value " + \
               f"{self.configurable_field_value} on permission {self.permission_pk}"

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):

        self.instantiate_fields()
        configuration = self.permission.get_configuration()

        configuration[self.configurable_field_name] = self.configurable_field_value
        self.permission.set_configuration(configuration)

        self.permission.save()
        return self.permission


class ChangeInverseStateChange(PermissionResourceBaseStateChange):
    """State change to toggle the inverse field of a permission."""

    description = "Toggle permission's inverse field"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, change_to: bool, permission_pk: int):
        self.change_to = change_to
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        return f"change inverse field to value {self.change_to} on permission {self.permission_pk} " + \
               f"({self.permission.get_change_type})"

    def description_past_tense(self):
        return f"changed inverse field to value {self.change_to} on permission {self.permission_pk} " + \
               f"({self.permission.get_change_type})"

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.inverse = self.change_to
        self.permission.save()
        return self.permission


class EnableAnyoneStateChange(PermissionResourceBaseStateChange):
    """State change to set a permission so anyone can take it."""

    description = "Give anyone permission"
    preposition = "for"

    def __init__(self, *, permission_pk: int):
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        return f"give anyone permission {self.permission_pk}"

    def description_past_tense(self):
        return f"gave anyone permission {self.permission_pk}"

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):
        permission = self.look_up_permission()
        permission.anyone = True
        permission.save()
        return permission


class DisableAnyoneStateChange(PermissionResourceBaseStateChange):
    """State change which takes a permission that has 'anyone' enabled, so anyone can take it, and disables
    it so only the roles and actors specified can take it.."""

    description = "Remove anyone from permission"
    preposition = "for"

    def __init__(self, *, permission_pk: int):
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        return f"remove anyone from permission {self.permission_pk}"

    def description_past_tense(self):
        return f"removed anyone from permission {self.permission_pk}"

    def validate(self, actor, target):
        # put real logic here
        return True

    def implement(self, actor, target):
        permission = self.look_up_permission()
        permission.anyone = False
        permission.save()
        return permission


class AddPermissionConditionStateChange(PermissionResourceBaseStateChange):
    """State change to add a condition to a permission."""
    description = "Add condition to permission"

    def __init__(self, *, permission_pk, condition_type, condition_data, permission_data):
        self.permission_pk = permission_pk
        self.condition_type = condition_type
        self.condition_data = condition_data
        self.permission_data = permission_data if permission_data else []

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        return f"add condition {self.condition_type} to permission"

    def description_past_tense(self):
        return f"added condition {self.condition_type} to permission"

    def generate_mock_actions(self, actor, permission):
        """Helper method with template generation logic, since we're using it in both validate and implement.
        The actions below are stored within the template, and copied+instantiated when a separate action triggers
        the permission to do so."""

        client = Client(actor=actor)
        client.Conditional.mode = "mock"
        client.PermissionResource.mode = "mock"

        mock_action_list = []
        action_1 = client.Conditional.set_condition_on_action(
            condition_type=self.condition_type, condition_data=self.condition_data, permission_pk=permission.pk)
        action_1.target = "{{trigger_action}}"
        mock_action_list.append(action_1)

        client.PermissionResource.target = action_1
        for permission_item_data in self.permission_data:
            next_action = client.PermissionResource.add_permission(**permission_item_data)
            next_action.target = "{{previous.0.result}}"
            mock_action_list.append(next_action)

        return mock_action_list

    def validate(self, actor, target):

        try:
            int(self.permission_pk)
        except TypeError:
            self.set_validation_error(message="permission_pk must be value that can be an int, " +
                                      f"not {self.permission_pk}")
            return False

        if not self.condition_type:
            self.set_validation_error(message="condition_type cannont be None")

        permission = self.look_up_permission()
        try:
            self.generate_mock_actions(actor, permission)
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False

    def implement(self, actor, target):

        permission = self.look_up_permission()

        permission.condition.action_list = self.generate_mock_actions(actor, permission)
        condition_action = permission.condition.action_list[0]
        permissions_actions = permission.condition.action_list[1:]

        permission.condition.description = condition_template_to_text(condition_action, permissions_actions)

        permission.save()
        return permission


class RemovePermissionConditionStateChange(PermissionResourceBaseStateChange):
    """State change to remove a condition from a permission."""
    description = "Remove condition from permission"

    def __init__(self, *, permission_pk: int):
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [Resource, Item, PermissionsItem]

    def description_present_tense(self):
        return "remove condition from permission"

    def description_past_tense(self):
        return "removed condition from permission"

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        permission = self.look_up_permission()
        permission.condition.action_list = []
        permission.save()
        return permission


##############################
### Template State Changes ###
##############################


class EditTemplateStateChange(BaseStateChange):
    """State change to edit a template."""
    description = "Edit Template"

    def __init__(self, template_object_id, field_name, new_field_data):
        self.template_object_id = template_object_id
        self.field_name = field_name
        self.new_field_data = new_field_data

    @classmethod
    def get_settable_classes(cls):
        return [Template]

    def description_present_tense(self):
        return f"edit template field {self.field_name} to {self.new_field_data}"

    def description_past_tense(self):
        return f"edited template field {self.field_name} to {self.new_field_data}"

    def validate(self, actor, target):
        """
        put real logic here
        """
        result = target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        if result.__class__.__name__ == "ValidationError":
            self.set_validation_error(result.message)
            return False
        return True

    def implement(self, actor, target):

        target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        target.save()

        return target
