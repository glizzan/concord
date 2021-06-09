"""Community state changes."""

from django.core.exceptions import ValidationError

from concord.actions.state_changes import BaseStateChange
from concord.utils.text_utils import list_to_text
from concord.utils.helpers import Client
from concord.utils import field_utils


###############################
### Community State Changes ###
###############################


class ChangeNameStateChange(BaseStateChange):
    """State change to change name of Community."""

    descriptive_text = {
        "verb": "change",
        "default_string": "name of community",
        "detail_string": "nameof community to {name}",
        "preposition": "for"
    }

    section = "Community"
    model_based_validation = ("target", ["name"])
    allowable_targets = ["all_community_models"]

    name = field_utils.CharField(label="New name", required=True)

    def implement(self, actor, target, **kwargs):
        target.name = self.name
        target.save()
        return target


class AddMembersStateChange(BaseStateChange):
    """State change to add members to Community."""

    descriptive_text = {
        "verb": "add",
        "default_string": "members to community",
        "detail_string": "{member_pk_list} as members"
    }

    section = "Community"
    allowable_targets = ["all_community_models"]
    linked_filters = ["SelfMembershipFilter"]

    member_pk_list = field_utils.ActorListField(label="People to add as members", required=True)

    def validate(self, actor, target):
        if not isinstance(self.member_pk_list, list):
            raise ValidationError(f"member_pk_list must be list, not {type(self.member_pk_list)}")
        if not all([isinstance(member_pk, int) for member_pk in self.member_pk_list]):
            raise ValidationError(message="member_pk_list must contain only integers")

    def implement(self, actor, target, **kwargs):
        target.roles.add_members(self.member_pk_list)
        target.save()
        return target


class RemoveMembersStateChange(BaseStateChange):
    """State change to remove members from Community."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "members from community",
        "detail_string": "members {member_pk_list} from community",
        "preposition": "from"
    }

    section = "Community"
    linked_filters = ["SelfMembershipFilter"]
    allowable_targets = ["all_community_models"]

    member_pk_list = field_utils.ActorListField(label="People to remove as members", required=True)

    def validate(self, actor, target):
        """If any of the members to be removed are an owner or governor (either directly, or through
        being in an owner or governor role) the action is not valid."""

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
            raise ValidationError(message)

    def implement(self, actor, target, **kwargs):

        # Remove members from custom roles
        for role_name in target.roles.get_custom_roles():
            target.roles.remove_people_from_role(role_name, self.member_pk_list)
        # Now remove them from members
        target.roles.remove_members(self.member_pk_list)

        target.save()
        return target


class ChangeGovernorsStateChange(BaseStateChange):
    """State change to add or remove governors from Community."""

    descriptive_text = {
        "verb": "change",
        "default_string": "governors of community"
    }

    is_foundational = True
    section = "Leadership"
    allowable_targets = ["all_community_models"]

    roles_to_add = field_utils.ActorField(label="Roles to add")
    roles_to_remove = field_utils.ActorField(label="Roles to remove")
    actors_to_add = field_utils.ActorField(label="People to add")
    actors_to_remove = field_utils.ActorField(label="People to remove")

    def make_changes(self, actor, target):

        if self.actors_to_add:
            [target.roles.add_governor(pk) for pk in self.actors_to_add]

        if self.actors_to_remove:
            [target.roles.remove_governor(pk) for pk in self.actors_to_remove]

        if self.roles_to_add:
            [target.roles.add_governor_role(role) for role in self.roles_to_add]

        if self.roles_to_remove:
            [target.roles.remove_governor_role(role) for role in self.roles_to_remove]

        return target

    def validate(self, actor, target):
        if not self.roles_to_add and not self.roles_to_remove and \
            not self.actors_to_add and not self.actors_to_remove:
            raise ValidationError("Must add or remove at least one individual governor or governing role.")
        target = self.make_changes(actor, target)
        target.roles.validate_role_handler()
        target.refresh_from_db()

    def implement(self, actor, target, **kwargs):
        target = self.make_changes(actor, target)
        target.save()
        return target


class ChangeOwnersStateChange(BaseStateChange):
    """State change to add or remove owners from Community."""

    descriptive_text = {
        "verb": "change",
        "default_string": "owners of community"
    }

    is_foundational = True
    section = "Leadership"
    allowable_targets = ["all_community_models"]

    roles_to_add = field_utils.RoleListField(label="Roles to add")
    roles_to_remove = field_utils.RoleListField(label="Roles to remove")
    actors_to_add = field_utils.ActorListField(label="People to add")
    actors_to_remove = field_utils.ActorListField(label="People to remove")

    def make_changes(self, actor, target):

        if self.actors_to_add:
            [target.roles.add_owner(pk) for pk in self.actors_to_add]

        if self.actors_to_remove:
            [target.roles.remove_owner(pk) for pk in self.actors_to_remove]

        if self.roles_to_add:
            [target.roles.add_owner_role(role) for role in self.roles_to_add]

        if self.roles_to_remove:
            [target.roles.remove_owner_role(role) for role in self.roles_to_remove]

        return target

    def validate(self, actor, target):
        if not self.roles_to_add and not self.roles_to_remove and not self.actors_to_add \
            and not self.actors_to_remove:
            raise ValidationError("Must add or remove at least one individual owner or owning role.")
        target = self.make_changes(actor, target)
        target.roles.validate_role_handler()
        target.refresh_from_db()

    def implement(self, actor, target, **kwargs):
        target = self.make_changes(actor, target)
        target.save()
        return target


class AddRoleStateChange(BaseStateChange):
    """State change to add role to Community."""

    descriptive_text = {
        "verb": "add",
        "default_string": "role to community",
        "detail_string": "role {role_name} to community",
    }

    section = "Community"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to add to community", required=True)

    def validate(self, actor, target):
        if self.role_name in ["members", "governors", "owners"]:
            raise ValidationError("Role name cannot be one of protected names: members, governors, owners.")
        if target.roles.is_role(self.role_name):
            raise ValidationError("The role " + self.role_name + " already exists.")

    def implement(self, actor, target, **kwargs):
        target.roles.add_role(self.role_name)
        target.save()
        return target


class RemoveRoleStateChange(BaseStateChange):
    """State change to remove role from Community."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "role from community",
        "detail_string": "role {role_name}",
        "preposition": "from"
    }

    section = "Community"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to remove from community", required=True)

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

        role_references = []
        client = Client(actor=actor, target=target)
        for permission in client.PermissionResource.get_all_permissions():
            role_references += self.role_in_permissions(permission, actor)

        if len(role_references) > 0:
            permission_string = ", ".join([str(permission.pk) for permission in role_references])
            raise ValidationError(f"Role cannot be deleted until it is removed from permissions: {permission_string}")

        if self.role_name in target.roles.get_owners()["roles"]:
            raise ValidationError("Cannot remove role with ownership privileges")
        if self.role_name in target.roles.get_governors()["roles"]:
            raise ValidationError("Cannot remove role with governorship privileges")

    def implement(self, actor, target, **kwargs):
        target.roles.remove_role(self.role_name)
        target.save()
        return target


class AddPeopleToRoleStateChange(BaseStateChange):
    """State change to add people to role in Community."""

    descriptive_text = {
        "verb": "add",
        "default_string": "people to role",
        "detail_string": "people {people_to_add} to role '{role_name}'",
        "preposition": "in"
    }

    section = "Community"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to add people to", required=True)
    people_to_add = field_utils.ActorListField(label="People to add to role", required=True)

    linked_filters = ["RoleMatchesFilter"]

    def is_conditionally_foundational(self, action):
        """If role_name is owner or governor role, should should be treated as a conditional change."""
        if self.role_name in action.target.roles.get_owners()["roles"]:
            return True
        if self.role_name in action.target.roles.get_governors()["roles"]:
            return True
        return False

    def validate(self, actor, target):
        if not isinstance(self.role_name, str):
            raise ValidationError(f"Role must be type str, not {str(type(self.role_name))}")
        if not target.roles.is_role(self.role_name):
            raise ValidationError(f"Role {self.role_name} does not exist")
        people_already_in_role = []
        for person in self.people_to_add:
            if target.roles.has_specific_role(self.role_name, person):
                people_already_in_role.append(str(person))
        if people_already_in_role:
            raise ValidationError(f"Users {list_to_text(people_already_in_role)} already in role {self.role_name}")

    def implement(self, actor, target, **kwargs):
        target.roles.add_people_to_role(self.role_name, self.people_to_add)
        target.save()
        return target


class RemovePeopleFromRoleStateChange(BaseStateChange):
    """State change to remove people from role in Community."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "people from role",
        "detail_string": "people {people_to_remove} from role '{role_name}'",
        "preposition": "in"
    }

    section = "Community"
    allowable_targets = ["all_community_models"]

    role_name = field_utils.RoleField(label="Role to remove people from", required=True)
    people_to_remove = field_utils.ActorListField(label="People to remove from role", required=True)

    def is_conditionally_foundational(self, action):
        """If role_name is owner or governor role, should should be treated as a conditional
        change."""
        if self.role_name in action.target.roles.get_owners()["roles"]:
            return True
        if self.role_name in action.target.roles.get_governors()["roles"]:
            return True
        return False

    def validate(self, actor, target):
        """When removing people from a role, we must check that doing so does not leave us
        without any owners."""

        if self.role_name not in target.roles.get_owners()["roles"]:
            return  # this isn't an owner role

        if len(self.people_to_remove) < len(target.roles.get_users_given_role(self.role_name)):
            return  # removing these users will not result in empty role

        if len(target.roles.get_owners()["actors"]) > 0:
            return  # community has individual actor owners so it doesn't need roles

        for role in target.roles.get_owners()["roles"]:
            if role == self.role_name:
                continue
            actors = target.roles.get_users_given_role(role)
            if len(actors) > 0:
                return  # there are other owner roles with actors specified

        raise ValidationError("Cannot remove everyone from this role as " +
                              "doing so would leave the community without an owner")

    def implement(self, actor, target, **kwargs):
        target.roles.remove_people_from_role(self.role_name, self.people_to_remove)
        target.save()
        return target
