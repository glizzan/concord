"""Get state changes for permissions resources."""

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from concord.actions.state_changes import BaseStateChange
from concord.permission_resources.models import PermissionsItem
from concord.utils.text_utils import get_verb_given_permission_type
from concord.utils.lookups import get_state_change_object
from concord.actions.models import TemplateModel
from concord.permission_resources.utils import delete_permissions_on_target
from concord.utils import field_utils
from concord.conditionals.utils import validate_condition
from concord.conditionals.models import ConditionManager


logger = logging.getLogger(__name__)


################################
### Permission State Changes ###
################################


class AddPermissionStateChange(BaseStateChange):
    """State change to add a permission to something."""

    descriptive_text = {            # note that description_present_tense and past tense are overridden below
        "verb": "add",
        "default_string": "permission"
    }

    section = "Permissions"
    model_based_validation = (PermissionsItem, ["change_type", "anyone", "inverse"])

    change_type = field_utils.CharField(label="Type of action the permission covers", required=True)
    actors = field_utils.ActorListField(label="Actors who have this permission", null_value=list)
    roles = field_utils.RoleListField(label="Roles who have this permission", null_value=list)
    anyone = field_utils.BooleanField(label="Everyone has the permission", null_value=False)
    inverse = field_utils.BooleanField(label="Do the inverse of this permission", null_value=False)
    condition_data = field_utils.CharField(label="Condition for this permission")

    def description_present_tense(self):
        return f"add permission '{get_verb_given_permission_type(self.change_type)}'"

    def description_past_tense(self):
        return f"added permission '{get_verb_given_permission_type(self.change_type)}'"

    def is_conditionally_foundational(self, action):
        """Some state changes are only foundational in certain conditions. Those state changes override this
        method to apply logic and determine whether a specific instance is foundational or not."""
        from concord.utils.lookups import get_state_change_object
        change_object = get_state_change_object(self.change_type)
        return action.change.is_foundational

    def validate(self, actor, target):

        permission = get_state_change_object(self.change_type)

        # check that target is a valid class for the permission to be set on
        if target.__class__ not in permission.get_settable_classes():
            settable_classes_str = ", ".join([str(option) for option in permission.get_settable_classes()])
            raise ValidationError(f"This kind of permission cannot be set on target {target} of class " +
                                  f"{target.__class__}, must be {settable_classes_str}")

        # validate condition data
        if self.condition_data:
            for condition in self.condition_data:
                is_valid, message = validate_condition(condition["condition_type"],
                    condition["condition_data"], condition["permission_data"], target)
                if not is_valid:
                    raise ValidationError(message)

    def implement(self, actor, target, **kwargs):

        permission = PermissionsItem()
        permission.set_fields(
            owner=target.get_owner(), permitted_object=target, anyone=self.anyone, change_type=self.change_type,
            inverse=self.inverse, actors=self.actors, roles=self.roles)
        permission.save()

        # if condition, add and save
        if self.condition_data:

            # create initial manager
            owner = permission.get_owner()
            manager = ConditionManager.objects.create(owner=owner, community=owner.pk, set_on="permission")
            permission.condition = manager

            # add conditions
            for condition in self.condition_data:
                data = {"condition_type": condition["condition_type"], "condition_data": condition["condition_data"],
                        "permission_data": condition["permission_data"]}
                manager.add_condition(data_for_condition=data)
                manager.save()

        return permission


class EditPermissionStateChange(BaseStateChange):

    descriptive_text = {
        "verb": "edit",
        "default_string": "permission",
        "preposition": "on"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]
    model_based_validation = (PermissionsItem, ["anyone", "roles", "actors"])

    actors = field_utils.ActorListField(label="Actors who have this permission", null_value=list)
    roles = field_utils.RoleListField(label="Roles who have this permission", null_value=list)
    anyone = field_utils.BooleanField(label="Everyone has the permission", null_value=False)

    def validate(self, actor, target):
        if not self.actors and not self.roles and not self.anyone:
            raise ValidationError("Must change at least one field to edit permission.")

    def implement(self, actor, target, **kwargs):
        field_dict = {}
        if self.actors: field_dict["actors"] = self.actors
        if self.roles: field_dict["roles"] = self.roles
        if self.anyone: field_dict["anyone"] = self.anyone
        target.set_fields(**field_dict)
        target.save()
        return target


class RemovePermissionStateChange(BaseStateChange):
    """State change to remove a permission from something."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "permission",
        "preposition": "from"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    def implement(self, actor, target, **kwargs):
        try:
            pk = target.pk
            delete_permissions_on_target(target)
            target.delete()
            return pk
        except ObjectDoesNotExist as exception:
            logger.warning(exception)
            return False


class AddActorToPermissionStateChange(BaseStateChange):
    """State change to add an actor to a permission."""

    descriptive_text = {
        "verb": "add",
        "default_string": "actor to permission",
        "detail_string": "actor {actor} to permission",
        "preposition": "for"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    actor = field_utils.ActorField(label="Actor to add", required=True)

    def validate(self, actor, target):
        if not isinstance(self.actor, str):
            raise ValidationError(f"Actor must be passed as string not {type(self.actor)}")

    def implement(self, actor, target, **kwargs):
        target.actors.add_actors(actors=[self.actor])
        target.save()
        return target


class RemoveActorFromPermissionStateChange(BaseStateChange):
    """State change to remove an actor from a permission."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "actor from permission",
        "detail_string": "actor {actor} from permission",
        "preposition": "for"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    actor = field_utils.ActorField(label="Actor to remove", required=True)

    def validate(self, actor, target):
        if target.actors.actor_in_list(int(self.actor)):
            raise ValidationError(f"Actor {self.actor} is not set as an actor on this " +
                                  "permission so they cannot be removed.")

    def implement(self, actor, target, **kwargs):
        target.actors.remove_actors(actors=[self.actor])
        target.save()
        return target


class AddRoleToPermissionStateChange(BaseStateChange):
    """State change to add a role to a permission."""

    descriptive_text = {
        "verb": "add",
        "default_string": "role to permission",
        "detail_string": "role {role_name} to permission",
        "preposition": "for"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    role_name = field_utils.RoleField(label="Role to add", required=True)

    def validate(self, actor, target):
        community_owner = target.get_owner()
        if not community_owner.roles.is_role(self.role_name):
            raise ValidationError(f"{self.role_name} is not a role and so can't be set on permission")

    def implement(self, actor, target, **kwargs):
        target.add_role_to_permission(role=self.role_name)
        target.save()
        return target


class RemoveRoleFromPermissionStateChange(BaseStateChange):
    """State change to remove a role from a permission."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "role from permission",
        "detail_string": "role {role_name} from permission",
        "preposition": "for"
    }

    section = "Permissions"
    linked_filters = ["RoleMatchesFilter"]
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    role_name = field_utils.RoleField(label="Role to remove", required=True)

    def validate(self, actor, target):
        if not target.roles.role_name_in_list(self.role_name):
            raise ValidationError(f"{self.role_name} isn't a role on this permission so can't be removed")

    def implement(self, actor, target, **kwargs):
        target.remove_role_from_permission(role=self.role_name)
        target.save()
        return target


class ChangeInverseStateChange(BaseStateChange):
    """State change to toggle the inverse field of a permission."""

    descriptive_text = {
        "verb": "toggle",
        "default_string": "inverse field on permission",
        "detail_string": "inverse field on permission to {change_to}",
        "preposition": "for"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    change_to = field_utils.BooleanField(label="Change inverse field of permission to", required=True)

    def validate(self, actor, target):
        if not isinstance(self.change_to, bool):
            raise ValidationError(f"'change_to' must be True or False, not {type(self.change_to)}")

    def implement(self, actor, target, **kwargs):
        target.inverse = self.change_to
        target.save()
        return target


class EnableAnyoneStateChange(BaseStateChange):
    """State change to set a permission so anyone can take it."""

    descriptive_text = {
        "verb": "give",
        "default_string": "anyone permission",
        "preposition": "for"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    def implement(self, actor, target, **kwargs):
        target.anyone = True
        target.save()
        return target


class DisableAnyoneStateChange(BaseStateChange):
    """State change which takes a permission that has 'anyone' enabled, so anyone can take it, and disables
    it so only the roles and actors specified can take it.."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "anyone from permission",
        "preposition": "for"
    }

    section = "Permissions"
    allowable_targets = [PermissionsItem]
    settable_classes = ["all_models"]

    def implement(self, actor, target, **kwargs):
        target.anyone = False
        target.save()
        return target


##############################
### Template State Changes ###
##############################


class EditTemplateStateChange(BaseStateChange):
    """State change to edit a template."""

    descriptive_text = {
        "verb": "edit",
        "default_string": "template",
        "detail_string": "template field {field_name} to new value {new_field_data}"
    }

    allowable_targets = [TemplateModel]
    settable_classes = ["all_models"]

    template_object_id = field_utils.IntegerField(label="ID of Template to edit", required=True)
    field_name = field_utils.CharField(label="Field to edit", required=True)
    new_field_data = field_utils.DictField(label="Data to edit", required=True)

    def validate(self, actor, target):
        result = target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        if result.__class__.__name__ == "ValidationError":
            raise result

    def implement(self, actor, target, **kwargs):

        target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        target.save()

        return target
