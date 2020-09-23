"""Get state changes for permissions resources."""

import logging

from django.core.exceptions import ValidationError, ObjectDoesNotExist

from concord.actions.state_changes import BaseStateChange, InputField
from concord.permission_resources.models import PermissionsItem
from concord.actions.text_utils import condition_template_to_text, get_verb_given_permission_type
from concord.actions.utils import get_state_change_object, Client
from concord.permission_resources.models import Template
from concord.permission_resources.utils import delete_permissions_on_target


logger = logging.getLogger(__name__)


################################
### Permission State Changes ###
################################


class AddPermissionStateChange(BaseStateChange):
    """State change to add a permission to something."""
    description = "Add permission"
    section = "Permissions"
    input_fields = [InputField(name="change_type", type="CharField", required=True, validate=True),
                    InputField(name="actors", type="ActorListField", required=True, validate=True),
                    InputField(name="roles", type="RoleListField", required=True, validate=True),
                    InputField(name="configuration", type="DictField", required=False, validate=True),
                    InputField(name="anyone", type="BooleanField", required=False, validate=True),
                    InputField(name="inverse", type="BooleanField", required=False, validate=True)]
    input_target = PermissionsItem

    def __init__(self, change_type, actors, roles, configuration=None, anyone=False, inverse=False):
        """Permission actors and permission role pairs MUST be a list of zero or more
        strings."""
        self.change_type = change_type
        self.actors = actors if actors else []
        self.roles = roles if roles else []
        self.configuration = configuration if configuration else {}
        self.inverse = inverse
        self.anyone = anyone

    def description_present_tense(self):
        config_str = f" (configuration: {str(self.configuration)})" if self.configuration else ""
        return f"add permission '{get_verb_given_permission_type(self.change_type)}" + config_str + "'"

    def description_past_tense(self):
        config_str = f" (configuration: {str(self.configuration)})" if self.configuration else ""
        return f"added permission '{get_verb_given_permission_type(self.change_type)}" + config_str + "'"

    def is_conditionally_foundational(self, action):
        """Some state changes are only foundational in certain conditions. Those state changes override this
        method to apply logic and determine whether a specific instance is foundational or not."""
        from concord.actions.utils import get_state_change_object
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

    def implement(self, actor, target):

        permission = PermissionsItem()
        permission.set_fields(
            owner=target.get_owner(), permitted_object=target, anyone=self.anyone, change_type=self.change_type,
            inverse=self.inverse, actors=self.actors, roles=self.roles, configuration=self.configuration
        )
        permission.save()
        return permission


class RemovePermissionStateChange(BaseStateChange):
    """State change to remove a permission from something."""
    description = "Remove permission"
    section = "Permissions"
    preposition = "from"

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "remove permission"

    def description_past_tense(self):
        return "removed permission"

    def implement(self, actor, target):
        try:
            delete_permissions_on_target(target)
            target.delete()
            return True
        except ObjectDoesNotExist as exception:
            logger.warning(exception)
            return False


class AddActorToPermissionStateChange(BaseStateChange):
    """State change to add an actor to a permission."""

    description = "Add actor to permission"
    preposition = "for"
    section = "Permissions"
    input_fields = [InputField(name="actor_to_add", type="ActorPKField", required=True, validate=False)]

    def __init__(self, *, actor_to_add: str):
        self.actor_to_add = actor_to_add

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

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

    def implement(self, actor, target):
        target.actors.add_actors(actors=[self.actor_to_add])
        target.save()
        return target


class RemoveActorFromPermissionStateChange(BaseStateChange):
    """State change to remove an actor from a permission."""
    description = "Remove actor from permission"
    preposition = "for"
    section = "Permissions"
    input_fields = [InputField(name="actor_to_remove", type="ActorPKField", required=True, validate=False)]

    def __init__(self, *, actor_to_remove: str):
        self.actor_to_remove = actor_to_remove

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

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

    def implement(self, actor, target):
        target.actors.remove_actors(actors=[self.actor_to_remove])
        target.save()
        return target


class AddRoleToPermissionStateChange(BaseStateChange):
    """State change to add a role to a permission."""

    description = "Add role to permission"
    preposition = "for"
    section = "Permissions"
    input_fields = [InputField(name="role_name", type="RoleField", required=True, validate=False)]

    def __init__(self, *, role_name: str):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

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

    def implement(self, actor, target):
        target.add_role_to_permission(role=self.role_name)
        target.save()
        return target


class RemoveRoleFromPermissionStateChange(BaseStateChange):
    """State change to remove a role from a permission."""

    description = "Remove role from permission"
    preposition = "for"
    section = "Permissions"
    input_fields = [InputField(name="role_name", type="RoleField", required=True, validate=False)]

    def __init__(self, *, role_name: str):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    @classmethod
    def get_configurable_fields(cls):
        return {"role_name": {
            "display": "Role that can be removed from the permission", "type": "RoleField"}}

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

    def implement(self, actor, target):
        target.remove_role_from_permission(role=self.role_name)
        target.save()
        return target


class ChangePermissionConfigurationStateChange(BaseStateChange):
    """State change to change the configuration of a permission."""

    description = "Change configuration of permission"
    preposition = "for"
    section = "Permissions"
    input_fields = [InputField(name="configurable_field_name", type="CharField", required=True, validate=False),
                    InputField(name="configurable_field_value", type="CharField", required=True, validate=False)]

    def __init__(self, *, configurable_field_name: str, configurable_field_value: str):
        self.configurable_field_name = configurable_field_name
        self.configurable_field_value = configurable_field_value

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return f"change configuration field {self.configurable_field_name} to value " + \
               f"{self.configurable_field_value} on permission"

    def description_past_tense(self):
        return f"changed configuration field {self.configurable_field_name} to value " + \
               f"{self.configurable_field_value} on permission"

    def implement(self, actor, target):

        configuration = target.get_configuration()

        configuration[self.configurable_field_name] = self.configurable_field_value
        target.set_configuration(configuration)

        target.save()
        return target


class ChangeInverseStateChange(BaseStateChange):
    """State change to toggle the inverse field of a permission."""

    description = "Toggle permission's inverse field"
    preposition = "for"
    section = "Permissions"
    input_fields = [InputField(name="change_to", type="BooleanField", required=True, validate=False)]

    def __init__(self, *, change_to: bool):
        self.change_to = change_to

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

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

    def implement(self, actor, target):
        target.inverse = self.change_to
        target.save()
        return target


class EnableAnyoneStateChange(BaseStateChange):
    """State change to set a permission so anyone can take it."""

    description = "Give anyone permission"
    section = "Permissions"
    preposition = "for"

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "give anyone permission"

    def description_past_tense(self):
        return "gave anyone permission"

    def implement(self, actor, target):
        target.anyone = True
        target.save()
        return target


class DisableAnyoneStateChange(BaseStateChange):
    """State change which takes a permission that has 'anyone' enabled, so anyone can take it, and disables
    it so only the roles and actors specified can take it.."""
    description = "Remove anyone from permission"
    section = "Permissions"
    preposition = "for"

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "remove anyone from permission"

    def description_past_tense(self):
        return "removed anyone from permission"

    def implement(self, actor, target):
        target.anyone = False
        target.save()
        return target


class AddPermissionConditionStateChange(BaseStateChange):
    """State change to add a condition to a permission."""
    description = "Add condition to permission"
    section = "Permissions"
    input_fields = [InputField(name="condition_type", type="CharField", required=True, validate=False),
                    InputField(name="condition_data", type="DictField", required=True, validate=False),
                    InputField(name="permission_data", type="DictField", required=True, validate=False)]

    def __init__(self, *, condition_type, condition_data, permission_data):
        self.condition_type = condition_type
        self.condition_data = condition_data
        self.permission_data = permission_data if permission_data else []

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

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
        action_1.target = "{{context.action}}"
        mock_action_list.append(action_1)

        client.PermissionResource.target = action_1
        for permission_item_data in self.permission_data:
            next_action = client.PermissionResource.add_permission(**permission_item_data)
            next_action.target = "{{previous.0.result}}"
            mock_action_list.append(next_action)

        return mock_action_list

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        if not self.condition_type:
            self.set_validation_error(message="condition_type cannot be None")
            return False

        try:
            self.generate_mock_actions(actor, target)
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False

    def implement(self, actor, target):

        target.condition.action_list = self.generate_mock_actions(actor, target)
        condition_action = target.condition.action_list[0]
        permissions_actions = target.condition.action_list[1:]

        target.condition.description = condition_template_to_text(condition_action, permissions_actions)

        target.save()
        return target


class RemovePermissionConditionStateChange(BaseStateChange):
    """State change to remove a condition from a permission."""
    description = "Remove condition from permission"
    section = "Permissions"

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "remove condition from permission"

    def description_past_tense(self):
        return "removed condition from permission"

    def implement(self, actor, target):
        target.condition.action_list = []
        target.save()
        return target


##############################
### Template State Changes ###
##############################


class EditTemplateStateChange(BaseStateChange):
    """State change to edit a template."""
    description = "Edit Template"
    input_fields = [InputField(name="template_object_id", type="ObjectIDField", required=True, validate=False),
                    InputField(name="field_name", type="CharField", required=True, validate=False),
                    InputField(name="new_field_data", type="DictField", required=True, validate=False)]

    def __init__(self, template_object_id, field_name, new_field_data):
        self.template_object_id = template_object_id
        self.field_name = field_name
        self.new_field_data = new_field_data

    @classmethod
    def get_allowable_targets(cls):
        return [Template]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

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

    def implement(self, actor, target):

        target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        target.save()

        return target
