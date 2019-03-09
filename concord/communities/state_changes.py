from concord.actions.state_changes import BaseStateChange


###############################
### Community State Changes ###
###############################

class ChangeNameStateChange(BaseStateChange):
    name = "community_changename"

    def __init__(self, new_name):
        self.new_name = new_name

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
    name = "community_addgovernor"

    def __init__(self, governor_name):
        self.governor_name = governor_name

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
    name = "community_addgovernorrole"

    def __init__(self, role_name):
        self.role_name = role_name

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
    name = "community_addowner"

    def __init__(self, owner_name):
        self.owner_name = owner_name

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
    name = "community_addownerrole"

    def __init__(self, role_name):
        self.role_name = role_name

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
    name = "community_addrole"

    def __init__(self, role_name):
        self.role_name = role_name
        
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
    name = "community_removerole"

    def __init__(self, role_name):
        self.role_name = role_name

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roleset.remove_assigned_role(self.role_name)
        target.roleset.save()
        return target


class AddPeopleToRoleStateChange(BaseStateChange):
    name = "community_addpeopletorole"

    def __init__(self, role_name, people_to_add):
        self.role_name = role_name
        self.people_to_add = people_to_add
        
    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roleset.add_people_to_role(self.role_name, self.people_to_add)
        target.roleset.save()
        return target


class RemovePeopleFromRoleStateChange(BaseStateChange):
    name = "community_removepeoplefromrole"

    def __init__(self, role_name, people_to_remove):
        self.role_name = role_name
        self.people_to_remove = people_to_remove
        
    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.roleset.remove_people_from_role(self.role_name, self.people_to_remove)
        target.roleset.save()
        return target
