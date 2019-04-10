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
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]    

    def description_present_tense(self):
        return "change name of community to %s" % (self.new_name)  

    def description_past_tense(self):
        return "changed name of community to %s" % (self.new_name) 

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        if actor and target and self.new_name:
            return True
        return False

    def implement(self, actor, target):
        target.name = self.new_name
        target.save()
        return target


class AddGovernorStateChange(BaseStateChange):
    description = "Add governor of community"

    def __init__(self, governor_name):
        self.governor_name = governor_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.authorityhandler.add_governor(self.governor_name)
        target.authorityhandler.save()
        return target


class AddGovernorRoleStateChange(BaseStateChange):
    description = "Add role of governor to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        # NOTE: we assume the role added is ALWAYS in the target community
        target.authorityhandler.add_governor_role(self.role_name, target.pk)
        target.authorityhandler.save()
        return target


class AddOwnerStateChange(BaseStateChange):
    description = "Add owner to community"

    def __init__(self, owner_name):
        self.owner_name = owner_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        target.authorityhandler.add_owner(self.owner_name)
        target.authorityhandler.save()
        return target


class AddOwnerRoleStateChange(BaseStateChange):
    description = "Add role of owner to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        # FIXME: if we forget to accidentally add this state change to our list of foundational
        # changes we could have access issues
        # NOTE: we assume the role added is ALWAYS in the target community
        target.authorityhandler.add_owner_role(self.role_name, target.pk)
        target.authorityhandler.save()
        return target


class AddRoleStateChange(BaseStateChange):
    description = "Add role to community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def description_present_tense(self):
        return "add role %s to" % (self.role_name)  

    def description_past_tense(self):
        return "added role %s to" % (self.role_name) 

    def validate(self, actor, target):
        # maybe make sure 'governor' and 'owner' aren't specified here?
        return True

    # FIXME: I don't love how the target is the community but we're changing roleset (or
    # authority handler, above)
    def implement(self, actor, target):
        target.roleset.add_assigned_role(self.role_name)
        target.roleset.save()
        return target


class RemoveRoleStateChange(BaseStateChange):
    description = "Remove role from community"

    def __init__(self, role_name):
        self.role_name = role_name

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def description_present_tense(self):
        return "remove role %s from" % (self.role_name)  

    def description_past_tense(self):
        return "removed role %s from" % (self.role_name) 

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roleset.remove_assigned_role(self.role_name)
        target.roleset.save()
        return target


class AddPeopleToRoleStateChange(BaseStateChange):
    description = "Add people to role in community"

    def __init__(self, role_name, people_to_add):
        self.role_name = role_name
        self.people_to_add = people_to_add

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def description_present_tense(self):
        return "add %s to role %s in" % (", ".join(self.people_to_add), self.role_name)  

    def description_past_tense(self):
        return "added %s to role %s in" % (", ".join(self.people_to_add), self.role_name)  

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roleset.add_people_to_role(self.role_name, self.people_to_add)
        target.roleset.save()
        return target


class RemovePeopleFromRoleStateChange(BaseStateChange):
    description = "Remove people from role in community"

    def __init__(self, role_name, people_to_remove):
        self.role_name = role_name
        self.people_to_remove = people_to_remove

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        return [Community, SubCommunity, SuperCommunity]

    def description_present_tense(self):
        return "remove %s from role %s in" % (", ".join(self.people_to_remove), self.role_name)  

    def description_past_tense(self):
        return "removed %s from role %s in" % (", ".join(self.people_to_remove), self.role_name)  


    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roleset.remove_people_from_role(self.role_name, self.people_to_remove)
        target.roleset.save()
        return target
