from concord.actions.state_changes import BaseStateChange


###############################
### Community State Changes ###
###############################

class ChangeNameStateChange(BaseStateChange):
    description = "Change name of community"

    def __init__(self, new_name):
        self.new_name = new_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]    

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


class AddMemberStateChange(BaseStateChange):
    description = "Add member to community"

    def __init__(self, member_pk):
        self.member_pk = member_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "add %s as member in" % (self.member_pk)  

    def description_past_tense(self):
        return "added %s as member in" % (self.member_pk)  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        target.roles.add_member(self.member_pk) 
        target.save()
        return target


class AddMembersStateChange(BaseStateChange):
    description = "Add members to community"

    def __init__(self, member_pk_list):
        self.member_pk_list = member_pk_list

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "add %s as members in" % (", ".join(self.member_pk_list))  

    def description_past_tense(self):
        return "added %s as members in" % (", ".join(self.member_pk_list))  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        target.roles.add_members(self.member_pk_list) 
        target.save()
        return target


class RemoveMemberStateChange(BaseStateChange):
    description = "Remove mmember from community"

    def __init__(self, member_pk):
        self.member_pk = member_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "remove %s as member in" % (self.member_pk)  

    def description_past_tense(self):
        return "removed %s as member in" % (self.member_pk)  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        target.roles.remove_member(self.member_pk) 
        target.save()
        return target


class AddGovernorStateChange(BaseStateChange):
    description = "Add governor of community"

    def __init__(self, governor_pk):
        self.governor_pk = governor_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "add %s as governor in" % (self.governor_pk)  

    def description_past_tense(self):
        return "added %s as governor in" % (self.governor_pk)  

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

    def __init__(self, governor_pk):
        self.governor_pk = governor_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "remove %s as governor in" % (self.governor_pk)  

    def description_past_tense(self):
        return "removed %s as governor in" % (self.governor_pk)  

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.roles.remove_governor(self.governor_pk)  
        target.roles.save()
        return target


class AddGovernorRoleStateChange(BaseStateChange):
    description = "Add role of governor to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "add role %s as governor in" % (self.role_name)  

    def description_past_tense(self):
        return "added role %s as governor in" % (self.role_name)  

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

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "remove role %s as governor in" % (self.role_name)  

    def description_past_tense(self):
        return "removed role %s as governor in" % (self.role_name) 

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
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "add %s as owner in" % (self.owner_pk)  

    def description_past_tense(self):
        return "added %s as owner in" % (self.owner_pk)  

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

    def __init__(self, owner_pk):
        self.owner_pk = owner_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "remove %s as owner in" % (self.owner_pk)  

    def description_past_tense(self):
        return "removed %s as owner in" % (self.owner_pk) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.roles.remove_owner(owner_pk)
        target.save()
        return target


class AddOwnerRoleStateChange(BaseStateChange):
    description = "Add role of owner to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "add role %s as owner in" % (self.role_name)  

    def description_past_tense(self):
        return "added role %s as owner in" % (self.role_name) 

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

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "remove role %s as owner in" % (self.role_name)  

    def description_past_tense(self):
        return "remove role %s as owner in" % (self.role_name) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        # NOTE: we assume the role added is ALWAYS in the target community
        target.roles.remove_owner_role(self.role_name, target.pk)
        target.save()
        return target


class AddRoleStateChange(BaseStateChange):
    description = "Add role to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "add role %s to" % (self.role_name)  

    def description_past_tense(self):
        return "added role %s to" % (self.role_name) 

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

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "remove role %s from" % (self.role_name)  

    def description_past_tense(self):
        return "removed role %s from" % (self.role_name) 

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roles.remove_role(self.role_name)
        target.save()
        return target


class AddPeopleToRoleStateChange(BaseStateChange):
    description = "Add people to role in community"

    def __init__(self, role_name, people_to_add):
        self.role_name = role_name
        self.people_to_add = people_to_add

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    @classmethod 
    def get_configurable_fields(self):
        return ["role_name"]

    @classmethod
    def get_uninstantiated_description(self, **configuration_kwargs):
        """Takes in an arbitrary number of configuration kwargs and uses them to 
        create a description.  Does not reference fields passed on init."""
        role_name = configuration_kwargs.get("role_name", None)
        role_name = "'" + role_name + "'" if role_name else ""
        return "add people to role %s" % (role_name)

    def description_present_tense(self):
        return "add %s to role %s in" % (", ".join(self.people_to_add), self.role_name)  

    def description_past_tense(self):
        return "added %s to role %s in" % (", ".join(self.people_to_add), self.role_name)  

    def check_configuration(self, permission):
        '''All configurations must pass for the configuration check to pass.'''
        configuration = permission.get_configuration()
        if "role_name" in configuration:  
            if self.role_name not in configuration["role_name"]:
                return False, "Can't add people to role %s, allowable roles are: %s" % (self.role_name,
                    ", ".join(configuration["role_name"]))
        return True, None

    def validate(self, actor, target):
        if not target.roles.is_role(self.role_name):
            self.set_validation_error("Role " + self.role_name + " does not exist")
            return False
        people_already_in_role = []
        for person in self.people_to_add:
            if target.roles.has_specific_role(self.role_name, person):
                people_already_in_role.append(str(person))
        if people_already_in_role:
            message = "Users %s already in role %s " % (", ".join(people_already_in_role), self.role_name)
            self.set_validation_error(message)
            return False
        return True

    def implement(self, actor, target):
        target.roles.add_people_to_role(self.role_name, self.people_to_add)
        target.save()
        return target


class RemovePeopleFromRoleStateChange(BaseStateChange):
    description = "Remove people from role in community"

    def __init__(self, role_name, people_to_remove):
        self.role_name = role_name
        self.people_to_remove = people_to_remove

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        return [Community]

    def description_present_tense(self):
        return "remove %s from role %s in" % (", ".join(self.people_to_remove), self.role_name)  

    def description_past_tense(self):
        return "removed %s from role %s in" % (", ".join(self.people_to_remove), self.role_name)  

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roles.remove_people_from_role(self.role_name, self.people_to_remove)
        target.save()
        return target
