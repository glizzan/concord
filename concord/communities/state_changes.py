"""Community state changes."""

from concord.actions.state_changes import BaseStateChange
from concord.utils.text_utils import list_to_text
from concord.utils.helpers import Client

from concord.utils import field_utils


###############################
### Community State Changes ###
###############################


class ChangeNameStateChange(BaseStateChange):
    """State change to change name of Community."""
    change_description = "Change name of community"
    preposition = "for"
    section = "Community"
    model_based_validation = ("target", ["name"])
    allowable_targets = ["all_community_models"]

    name = field_utils.CharField(label="New name", required=True)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def description_present_tense(self):
        return f"change name of community to {self.name}"

    def description_past_tense(self):
        return f"changed name of community to {self.name}"

    def implement(self, actor, target, **kwargs):
        target.name = self.name
        target.save()
        return target


class AddMembersStateChange(BaseStateChange):
    """State change to add members to Community."""
    change_description = "Add members to community"
    section = "Community"
    configurable_fields = ["self_only"]
    allowable_targets = ["all_community_models"]

    member_pk_list = field_utils.ActorListField(label="People to add as members", required=True)
    self_only = field_utils.BooleanField(label="Only allow actor to add self as member")

    def __init__(self, member_pk_list, self_only=False):
        super().__init__()
        self.member_pk_list = member_pk_list
        self.self_only = self_only

    @classmethod
    def get_configured_field_text(cls, configuration):
        if "self_only" in configuration and configuration['self_only']:
            return ", but a user can only add themselves"
        return ""

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "self_only" in configuration and configuration["self_only"] is not None:
            if configuration["self_only"] not in [True, False, "True", "False", "true", "false"]:
                return False, f"self_only must be set to True or False, not {configuration['self_only']}"
        return True, ""

    def check_configuration(self, action, permission):
        configuration = permission.get_configuration()
        if "self_only" in configuration and configuration['self_only']:
            if len(self.member_pk_list) != 1 or self.member_pk_list[0] != action.actor.pk:
                return False, "self_only is set to true, so member_pk_list can contain only the pk of the actor"
        return True, None

    def description_present_tense(self):
        return f"add {list_to_text(self.member_pk_list)} as members"

    def description_past_tense(self):
        return f"added {list_to_text(self.member_pk_list)} as members"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False

        if not isinstance(self.member_pk_list, list):
            self.set_validation_error(message=f"member_pk_list must be list, not {type(self.member_pk_list)}")
            return False
        if not all([isinstance(member_pk, int) for member_pk in self.member_pk_list]):
            self.set_validation_error(message="member_pk_list must contain only integers")
            return False

        return True

    def implement(self, actor, target, **kwargs):
        target.roles.add_members(self.member_pk_list)
        target.save()
        return target


class RemoveMembersStateChange(BaseStateChange):
    """State change to remove members from Community."""
    change_description = "Remove members from community"
    preposition = "from"
    section = "Community"
    configurable_fields = ["self_only"]
    allowable_targets = ["all_community_models"]

    member_pk_list = field_utils.ActorListField(label="People to remove as members", required=True)
    self_only = field_utils.BooleanField(label="Only allow actor to remove self as member")

    def __init__(self, member_pk_list, self_only=False):
        super().__init__()
        self.member_pk_list = member_pk_list
        self.self_only = self_only

    def description_present_tense(self):
        return f"remove members {list_to_text(self.member_pk_list)}"

    def description_past_tense(self):
        return f"removed members {list_to_text(self.member_pk_list)}"

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "self_only" in configuration and configuration["self_only"] is not None:
            if configuration["self_only"] not in [True, False, "True", "False", "true", "false"]:
                return False, f"self_only must be set to True or False, not {configuration['self_only']}"
        return True, ""

    def check_configuration(self, action, permission):
        configuration = permission.get_configuration()
        if "self_only" in configuration and configuration['self_only']:
            if len(self.member_pk_list) != 1 or self.member_pk_list[0] != action.actor.pk:
                return False, "self_only is set to true, so member_pk_list can contain only the pk of the actor"
        return True, None

    def validate(self, actor, target):
        """If any of the members to be removed are an owner or governor (either directly, or through
        being in an owner or governor role) the action is not valid."""

        if not super().validate(actor=actor, target=target):
            return False

        governor_list, owner_list = [], []
        for pk in self.member_pk_list:
            is_governor, result = target.roles.is_governor(pk)
            if is_governor:
                governor_list.append(str(pk))
            is_owner, result = target.roles.is_owner(pk)
            if is_owner:
                owner_list.append(str(pk))
        if governor_list or owner_list:
            message = f"Cannot remove members as some are owners or governors. Owners: {', '.join(owner_list)}, " + \
                      f"Governors: {', '.join(governor_list)}"
            self.set_validation_error(message)
            return False
        return True

    def implement(self, actor, target, **kwargs):

        # Remove members from custom roles
        for role_name in target.roles.get_custom_roles():
            target.roles.remove_people_from_role(role_name, self.member_pk_list)
        # Now remove them from members
        target.roles.remove_members(self.member_pk_list)

        target.save()
        return target


class AddGovernorStateChange(BaseStateChange):
    """State change to add governor to Community."""
    change_description = "Add governor of community"
    is_foundational = True
    section = "Leadership"
    allowable_targets = ["all_community_models"]

    governor_pk = field_utils.ActorField(label="Person to add as governor", required=True)

    def __init__(self, governor_pk):
        super().__init__()
        self.governor_pk = governor_pk

    def description_present_tense(self):
        return f"add {self.governor_pk} as governor"

    def description_past_tense(self):
        return f"added {self.governor_pk} as governor"

    def implement(self, actor, target, **kwargs):
        target.roles.add_governor(self.governor_pk)
        target.save()
        return target


class RemoveGovernorStateChange(BaseStateChange):
    """State change to remove governor from Community."""
    change_description = "Remove governor from community"
    preposition = "from"
    section = "Leadership"
    is_foundational = True
    allowable_targets = ["all_community_models"]

    governor_pk = field_utils.ActorField(label="Person to remove as governor", required=True)

    def __init__(self, governor_pk):
        super().__init__()
        self.governor_pk = governor_pk

    def description_present_tense(self):
        return f"remove {self.governor_pk} as governor"

    def description_past_tense(self):
        return f"removed {self.governor_pk} as governor"

    def implement(self, actor, target, **kwargs):
        target.roles.remove_governor(self.governor_pk)
        target.save()
        return target


class AddGovernorRoleStateChange(BaseStateChange):
    """State change to add governor role to Community."""
    change_description = "Add role of governor to community"
    is_foundational = True
    section = "Leadership"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to make governor role", required=True)

    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name

    def description_present_tense(self):
        return f"add role {self.role_name} as governor"

    def description_past_tense(self):
        return f"added role {self.role_name} as governor"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False

        if not target.roles.is_role(self.role_name):
            self.set_validation_error(message=f"Role {self.role_name} must be role in community to be " +
                                      "made a governing role")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.roles.add_governor_role(self.role_name)
        target.save()
        return target


class RemoveGovernorRoleStateChange(BaseStateChange):
    """State change to remove governor role from Community."""
    change_description = "Remove role of governor from community"
    preposition = "from"
    section = "Leadership"
    is_foundational = True
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to remove from governor role", required=True)

    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name

    def description_present_tense(self):
        return f"remove role {self.role_name} as governor"

    def description_past_tense(self):
        return f"removed role {self.role_name} as governor"

    def implement(self, actor, target, **kwargs):
        target.roles.remove_governor_role(self.role_name)
        target.save()
        return target


class AddOwnerStateChange(BaseStateChange):
    """State change to add owner to Community."""
    change_description = "Add owner to community"
    is_foundational = True
    section = "Leadership"
    allowable_targets = ["all_community_models"]

    owner_pk = field_utils.ActorField(label="Person to add as owner", required=True)

    def __init__(self, owner_pk):
        super().__init__()
        self.owner_pk = owner_pk

    def description_present_tense(self):
        return f"add {self.owner_pk} as owner"

    def description_past_tense(self):
        return f"added {self.owner_pk} as owner"

    def implement(self, actor, target, **kwargs):
        target.roles.add_owner(self.owner_pk)
        target.save()
        return target


class RemoveOwnerStateChange(BaseStateChange):
    """State change remove owner from Community."""
    change_description = "Remove owner from community"
    preposition = "from"
    section = "Leadership"
    is_foundational = True
    allowable_targets = ["all_community_models"]

    owner_pk = field_utils.ActorField(label="Person to remove as owner", required=True)

    def __init__(self, owner_pk):
        super().__init__()
        self.owner_pk = owner_pk

    def description_present_tense(self):
        return f"remove {self.owner_pk} as owner"

    def description_past_tense(self):
        return f"removed {self.owner_pk} as owner"

    def validate(self, actor, target):
        """If removing the owner would leave the group with no owners, the action is invalid."""
        if not super().validate(actor=actor, target=target):
            return False

        if len(target.roles.get_owners()["actors"]) > 1:
            return True  # community has at least one more actor who is an owner

        for role in target.roles.get_owners()["roles"]:
            actors = target.roles.get_users_given_role(role)
            if len(actors) > 0:
                return True  # there are actors in owner roles so we don't need this one

        self.set_validation_error(message="Cannot remove owner as doing so would leave the community without an owner")
        return False

    def implement(self, actor, target, **kwargs):
        target.roles.remove_owner(self.owner_pk)
        target.save()
        return target


class AddOwnerRoleStateChange(BaseStateChange):
    """State change to add owner role to Community."""
    change_description = "Add role of owner to community"
    is_foundational = True
    section = "Leadership"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to make owner role", required=True)

    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name

    def description_present_tense(self):
        return f"add role {self.role_name} as owner"

    def description_past_tense(self):
        return f"added role {self.role_name} as owner"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False

        if not target.roles.is_role(self.role_name):
            self.set_validation_error(message=f"Role {self.role_name} must be role in community to be " +
                                      "made an owning role")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.roles.add_owner_role(self.role_name)
        target.save()
        return target


class RemoveOwnerRoleStateChange(BaseStateChange):
    """State change to remove owner role from Community."""
    change_description = "Remove role from owners of community"
    preposition = "from"
    section = "Leadership"
    is_foundational = True
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to remove as owner role", required=True)

    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name

    def description_present_tense(self):
        return f"remove role {self.role_name} as owner"

    def description_past_tense(self):
        return f"removed role {self.role_name} as owner"

    def validate(self, actor, target):
        """If removing the owner role would leave the group with no owners, the action is invalid."""
        if not super().validate(actor=actor, target=target):
            return False

        if self.role_name not in target.roles.get_owners()["roles"]:
            self.set_validation_error(f"{self.role_name} is not an owner role in this community")
            return False

        if len(target.roles.get_owners()["actors"]) > 0:
            return True  # community has individual actor owners so it doesn't need roles

        for role in target.roles.get_owners()["roles"]:
            if role == self.role_name:
                continue
            actors = target.roles.get_users_given_role(role)
            if len(actors) > 0:
                return True  # there are other owner roles with actors specified

        self.set_validation_error(message="Cannot remove this role as doing so would leave the community " +
                                  "without an owner")

    def implement(self, actor, target, **kwargs):
        target.roles.remove_owner_role(self.role_name)
        target.save()
        return target


class AddRoleStateChange(BaseStateChange):
    """State change to add role to Community."""
    change_description = "Add role to community"
    section = "Community"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to add to community", required=True)

    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name

    def description_present_tense(self):
        return f"add role {self.role_name}"

    def description_past_tense(self):
        return f"added role {self.role_name}"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False

        if self.role_name in ["members", "governors", "owners"]:
            self.set_validation_error("Role name cannot be one of protected names: members, governors, owners.")
            return False
        if target.roles.is_role(self.role_name):
            self.set_validation_error("The role " + self.role_name + " already exists.")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.roles.add_role(self.role_name)
        target.save()
        return target


class RemoveRoleStateChange(BaseStateChange):
    """State change to remove role from Community."""
    change_description = "Remove role from community"
    preposition = "from"
    section = "Community"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to remove from community", required=True)

    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name

    def description_present_tense(self):
        return f"remove role {self.role_name}"

    def description_past_tense(self):
        return f"removed role {self.role_name}"

    def role_in_permissions(self, permission, actor):
        """Checks for role in permission and returns True if it exists.  Checks in permissions
        which are nested on this permission as well."""
        role_references = []
        if permission.has_role(role=self.role_name):
            role_references.append(permission)
        client = Client(actor=actor, target=permission)
        for permission in client.PermissionResource.get_all_permissions():
            role_references += self.role_in_permissions(permission, actor)
        return role_references

    def validate(self, actor, target):
        """A role cannot be deleted without removing it from the permissions it's referenced in, and
        without removing it from owner and governor roles if it is there."""
        if not super().validate(actor=actor, target=target):
            return False

        role_references = []
        client = Client(actor=actor, target=target)
        for permission in client.PermissionResource.get_all_permissions():
            role_references += self.role_in_permissions(permission, actor)

        if len(role_references) > 0:
            permission_string = ", ".join([str(permission.pk) for permission in role_references])
            self.set_validation_error(
                f"Role cannot be deleted until it is removed from permissions: {permission_string}")
            return False

        if self.role_name in target.roles.get_owners()["roles"]:
            self.set_validation_error("Cannot remove role with ownership privileges")
            return False
        if self.role_name in target.roles.get_governors()["roles"]:
            self.set_validation_error("Cannot remove role with governorship privileges")
            return False

        return True

    def implement(self, actor, target, **kwargs):
        target.roles.remove_role(self.role_name)
        target.save()
        return target


class AddPeopleToRoleStateChange(BaseStateChange):
    """State change to add people to role in Community."""
    change_description = "Add people to role in community"
    preposition = "in"
    section = "Community"
    configurable_fields = ["role_name"]
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to add people to", required=True)
    people_to_add = field_utils.ActorListField(label="People to add to role", required=True)

    def __init__(self, role_name, people_to_add):
        super().__init__()
        self.role_name = role_name
        self.people_to_add = people_to_add

    def is_conditionally_foundational(self, action):
        """If role_name is owner or governor role, should should be treated as a conditional
        change."""
        if self.role_name in action.target.roles.get_owners()["roles"]:
            return True
        if self.role_name in action.target.roles.get_governors()["roles"]:
            return True
        return False

    @classmethod
    def get_uninstantiated_description(cls, **configuration_kwargs):
        """Takes in an arbitrary number of configuration kwargs and uses them to
        create a description.  Does not reference fields passed on init."""
        role_name = configuration_kwargs.get("role_name", None)
        return "add people to role" + f" '{role_name}'" if role_name else ""

    def description_present_tense(self):
        return f"add {list_to_text(self.people_to_add)} to role {self.role_name}"

    def description_past_tense(self):
        return f"added {list_to_text(self.people_to_add)} to role {self.role_name}"

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "role_name" in configuration and configuration["role_name"] is not None:
            if not isinstance(configuration["role_name"], str):
                return False, f"Role name must be sent as string, not {str(type(configuration['role_name']))}"
        return True, ""

    def check_configuration(self, action, permission):
        '''All configurations must pass for the configuration check to pass.'''
        configuration = permission.get_configuration()
        if "role_name" in configuration:
            if self.role_name not in configuration["role_name"]:
                return False, f"Can't add people to role {self.role_name}, only {configuration['role_name']}"
        return True, None

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False

        if not isinstance(self.role_name, str):
            self.set_validation_error(f"Role must be type str, not {str(type(self.role_name))}")
            return False
        if not target.roles.is_role(self.role_name):
            self.set_validation_error(f"Role {self.role_name} does not exist")
            return False
        people_already_in_role = []
        for person in self.people_to_add:
            if target.roles.has_specific_role(self.role_name, person):
                people_already_in_role.append(str(person))
        if people_already_in_role:
            message = f"Users {list_to_text(people_already_in_role)} already in role {self.role_name}"
            self.set_validation_error(message)
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.roles.add_people_to_role(self.role_name, self.people_to_add)
        target.save()
        return target


class RemovePeopleFromRoleStateChange(BaseStateChange):
    """State change to remove people from role in Community."""
    change_description = "Remove people from role in community"
    preposition = "in"
    section = "Community"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to remove people from", required=True)
    people_to_remove = field_utils.ActorListField(label="People to remove from role", required=True)

    def __init__(self, role_name, people_to_remove):
        super().__init__()
        self.role_name = role_name
        self.people_to_remove = people_to_remove

    def is_conditionally_foundational(self, action):
        """If role_name is owner or governor role, should should be treated as a conditional
        change."""
        if self.role_name in action.target.roles.get_owners()["roles"]:
            return True
        if self.role_name in action.target.roles.get_governors()["roles"]:
            return True
        return False

    def description_present_tense(self):
        return f"remove {list_to_text(self.people_to_remove)} from role {self.role_name}"

    def description_past_tense(self):
        return f"removed {list_to_text(self.people_to_remove)} from role {self.role_name}"

    def validate(self, actor, target):
        """When removing people from a role, we must check that doing so does not leave us
        without any owners."""

        if not super().validate(actor=actor, target=target):
            return False

        if self.role_name not in target.roles.get_owners()["roles"]:
            return True  # this isn't an owner role

        if len(self.people_to_remove) < len(target.roles.get_users_given_role(self.role_name)):
            return True  # removing these users will not result in empty role

        if len(target.roles.get_owners()["actors"]) > 0:
            return True  # community has individual actor owners so it doesn't need roles

        for role in target.roles.get_owners()["roles"]:
            if role == self.role_name:
                continue
            actors = target.roles.get_users_given_role(role)
            if len(actors) > 0:
                return True  # there are other owner roles with actors specified

        self.set_validation_error(message="Cannot remove everyone from this role as " +
                                  "doing so would leave the community without an owner")

        return False

    def implement(self, actor, target, **kwargs):
        target.roles.remove_people_from_role(self.role_name, self.people_to_remove)
        target.save()
        return target
