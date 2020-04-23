from concord.actions.state_changes import BaseStateChange
from django.conf import settings
from django.apps import apps

  

###############################
### Community State Changes ###
###############################

class ChangeNameStateChange(BaseStateChange):
    description = "Change name of community"
    preposition = "for"

    def __init__(self, new_name):
        self.new_name = new_name

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "change name of community to %s" % (self.new_name)  

    def description_past_tense(self):
        return "changed name of community to %s" % (self.new_name) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        if actor and target and self.new_name:
            return True
        self.set_validation_error("You must provide provide a new name")
        return False

    def implement(self, actor, target):
        target.name = self.new_name
        target.save()
        return target


class AddMembersStateChange(BaseStateChange):
    description = "Add members to community"

    def __init__(self, member_pk_list):
        self.member_pk_list = member_pk_list

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "add %s as members" % self.stringify_list(self.member_pk_list) 

    def description_past_tense(self):
        return "added %s as members" % self.stringify_list(self.member_pk_list) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        target.roles.add_members(self.member_pk_list) 
        target.save()
        return target


class RemoveMembersStateChange(BaseStateChange):
    description = "Remove members from community"
    preposition = "from"

    def __init__(self, member_pk_list):
        self.member_pk_list = member_pk_list

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "remove members %s" % self.stringify_list(self.member_pk_list)   

    def description_past_tense(self):
        return "removed members %s " % self.stringify_list(self.member_pk_list)   

    def validate(self, actor, target):
        governor_list, owner_list = [], []
        for pk in self.member_pk_list:
            is_governor, result = target.roles.is_governor(pk)
            if is_governor:
                governor_list.append(str(pk))
            is_owner, result = target.roles.is_owner(pk)
            if is_owner:
                owner_list.append(str(pk))
        if governor_list or owner_list:
            message = "Cannot remove members as some are owners or governors. Owners: %s, Governors: %s " % (
                ", ".join(owner_list), ", ".join(governor_list))
            self.set_validation_error(message)
            return False
        return True

    def implement(self, actor, target):
        # Remove members from custom roles
        for role_name, role_members in target.roles.get_custom_roles().items():
            target.roles.remove_people_from_role(role_name, self.member_pk_list)
        # Now remove them from members      
        target.roles.remove_members(self.member_pk_list) 
        target.save()
        return target


class AddGovernorStateChange(BaseStateChange):
    description = "Add governor of community"

    def __init__(self, governor_pk):
        self.governor_pk = governor_pk

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "add %s as governor" % (self.governor_pk)  

    def description_past_tense(self):
        return "added %s as governor" % (self.governor_pk)  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.roles.add_governor(self.governor_pk) 
        target.save()
        return target


class RemoveGovernorStateChange(BaseStateChange):
    description = "Remove governor from community"
    preposition = "from"

    def __init__(self, governor_pk):
        self.governor_pk = governor_pk

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "remove %s as governor" % (self.governor_pk)  

    def description_past_tense(self):
        return "removed %s as governor" % (self.governor_pk)  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.roles.remove_governor(self.governor_pk)  
        target.save()
        return target


class AddGovernorRoleStateChange(BaseStateChange):
    description = "Add role of governor to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "add role %s as governor" % (self.role_name)  

    def description_past_tense(self):
        return "added role %s as governor" % (self.role_name)  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        # NOTE: we assume the role added is ALWAYS in the target community
        target.roles.add_governor_role(self.role_name)
        target.save()
        return target


class RemoveGovernorRoleStateChange(BaseStateChange):
    description = "Remove role of governor from community"
    preposition = "from"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "remove role %s as governor" % (self.role_name)  

    def description_past_tense(self):
        return "removed role %s as governor" % (self.role_name) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        # NOTE: we assume the role added is ALWAYS in the target community
        target.roles.remove_governor_role(self.role_name)
        target.save()
        return target


class AddOwnerStateChange(BaseStateChange):
    description = "Add owner to community"

    def __init__(self, owner_pk):
        self.owner_pk = owner_pk

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "add %s as owner" % (self.owner_pk)  

    def description_past_tense(self):
        return "added %s as owner" % (self.owner_pk)  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.roles.add_owner(self.owner_pk)
        target.save()
        return target


class RemoveOwnerStateChange(BaseStateChange):
    description = "Remove owner from community"
    preposition = "from"

    def __init__(self, owner_pk):
        self.owner_pk = owner_pk

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "remove %s as owner" % (self.owner_pk)  

    def description_past_tense(self):
        return "removed %s as owner" % (self.owner_pk) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.roles.remove_owner(self.owner_pk)
        target.save()
        return target


class AddOwnerRoleStateChange(BaseStateChange):
    description = "Add role of owner to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "add role %s as owner" % (self.role_name)  

    def description_past_tense(self):
        return "added role %s as owner" % (self.role_name) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        # NOTE: we assume the role added is ALWAYS in the target community
        target.roles.add_owner_role(self.role_name)
        target.save()
        return target


class RemoveOwnerRoleStateChange(BaseStateChange):
    description = "Remove role from owners of community"
    preposition = "from"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "remove role %s as owner" % (self.role_name)  

    def description_past_tense(self):
        return "remove role %s as owner" % (self.role_name) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # NOTE: we assume the role added is ALWAYS in the target community
        target.roles.remove_owner_role(self.role_name)
        target.save()
        return target


class AddRoleStateChange(BaseStateChange):
    description = "Add role to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "add role %s" % (self.role_name)  

    def description_past_tense(self):
        return "added role %s" % (self.role_name) 

    def validate(self, actor, target):
        if self.role_name in ["members", "governors", "owners"]:
            self.set_validation_error("Role name cannot be one of protected names: members, governors, owners.")
            return False
        if target.roles.is_role(self.role_name):
            self.set_validation_error("The role " + self.role_name + " already exists.")
            return False
        # TODO: maybe enforce limits on length, letter content, etc, possibly referencing field validation?
        return True

    def implement(self, actor, target):
        target.roles.add_role(self.role_name)
        target.save()
        return target


class RemoveRoleStateChange(BaseStateChange):
    description = "Remove role from community"
    preposition = "from"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "remove role %s" % (self.role_name)  

    def description_past_tense(self):
        return "removed role %s" % (self.role_name) 

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roles.remove_role(self.role_name)
        target.save()
        return target


class AddPeopleToRoleStateChange(BaseStateChange):
    description = "Add people to role in community"
    preposition = "in"

    def __init__(self, role_name, people_to_add):
        self.role_name = role_name
        self.people_to_add = people_to_add

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    @classmethod 
    def get_configurable_fields(self):
        return { "role_name": { "display": "Role people can be added to", "type": "PermissionRoleField",
        "other_data": { "multiple": False } } }

    @classmethod
    def get_uninstantiated_description(self, **configuration_kwargs):
        """Takes in an arbitrary number of configuration kwargs and uses them to 
        create a description.  Does not reference fields passed on init."""
        role_name = configuration_kwargs.get("role_name", None)
        role_name = "'" + role_name + "'" if role_name else ""
        return "add people to role %s" % (role_name)

    def description_present_tense(self):
        return "add %s to role %s" % (self.stringify_list(self.people_to_add), self.role_name)  

    def description_past_tense(self):
        return "added %s to role %s" % (self.stringify_list(self.people_to_add), self.role_name)  

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "role_name" in configuration:
            if type(configuration["role_name"]) != str:
                return False, "Role name must be sent as string, not " + str(type(configuration["role_name"]))
        return True, ""

    def check_configuration(self, permission):
        '''All configurations must pass for the configuration check to pass.'''
        configuration = permission.get_configuration()
        if "role_name" in configuration:  
            if self.role_name not in configuration["role_name"]:
                return False, "Can't add people to role %s, configured role is %s" % (self.role_name,
                    configuration["role_name"])
        return True, None

    def validate(self, actor, target):
        if type(self.role_name) != str:
            self.set_validation_error("Role must be type str, not " + str(type(self.role_name)))
            return False
        if not target.roles.is_role(self.role_name):
            self.set_validation_error("Role " + self.role_name + " does not exist")
            return False
        people_already_in_role = []
        for person in self.people_to_add:
            if target.roles.has_specific_role(self.role_name, person):
                people_already_in_role.append(str(person))
        if people_already_in_role:
            message = "Users %s already in role %s " % (self.stringify_list(people_already_in_role), self.role_name)
            self.set_validation_error(message)
            return False
        return True

    def implement(self, actor, target):
        target.roles.add_people_to_role(self.role_name, self.people_to_add)
        target.save()
        return target


class RemovePeopleFromRoleStateChange(BaseStateChange):
    description = "Remove people from role in community"
    preposition = "in"

    def __init__(self, role_name, people_to_remove):
        self.role_name = role_name
        self.people_to_remove = people_to_remove

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return "remove %s from role %s" % (self.stringify_list(self.people_to_remove), self.role_name)  

    def description_past_tense(self):
        return "removed %s from role %s" % (self.stringify_list(self.people_to_remove), self.role_name)  

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roles.remove_people_from_role(self.role_name, self.people_to_remove)
        target.save()
        return target
