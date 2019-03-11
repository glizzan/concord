import json

# TODO: make these explicit abstract class and subclasses *have* to implement validate and
# implement

# TODO: I think there should be a good way to do the check caller here, so that when
# implementing this system a model can check that it's being called via a subclass of 
# this object, which is the only way for models to change I believe.

# TODO: instead of manually specifying name, name is appname_modelname which is called
# as needed.


class BaseStateChange(object):

    def validate(self, actor, target):
        ...

    def implement(self, actor, target):
        ...

    def get_change_type(self):
        return self.__module__ + "." + self.__class__.__name__

    # def get_change_type(self):
    #     return self.name

    def get_change_data(self):
        '''
        Given the python Change object, generates a json list of field names
        and values.
        '''
        return json.dumps(vars(self))


class ChangeOwnerStateChange(BaseStateChange):
    name = "base_ownerchange"

    def __init__(self, new_owner, new_owner_type):
        # NOTE: new_owner SHOULD be the PK of the owner but for now it is their name
        self.new_owner = new_owner
        self.new_owner_type = new_owner_type

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        target.owner = self.new_owner
        target.owner_type = self.new_owner_type
        target.save()
        return target


class EnableFoundationalPermissionStateChange(BaseStateChange):
    name = "base_enablefoundationalpermissionchange"

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        target.foundational_permission_enabled = True
        target.save()
        return target


class DisableFoundationalPermissionStateChange(BaseStateChange):
    name = "base_disablefoundationalpermissionchange"

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        target.foundational_permission_enabled = False
        target.save()
        return target


# TODO: create and add governing_permission_state_change here
def foundational_changes():
    return [
        'concord.communities.state_changes.AddGovernorStateChange',
        'concord.communities.state_changes.AddOwnerStateChange',
        'concord.communities.state_changes.AddGovernorRoleStateChange',
        'concord.communities.state_changes.AddOwnerRoleStateChange',
        'concord.actions.state_changes.EnableFoundationalPermissionStateChange',
        'concord.actions.state_changes.DisableFoundationalPermissionStateChange'
    ]


def create_change_object(change_type, change_data):
    """
    Finds change object using change_type and instantiates with change_data.
    """
    # appname, classname = change_type.split("_")
    # changeclass = import_string(appname + "." + "state_changes." + classname)
    from django.utils.module_loading import import_string
    changeClass = import_string(change_type)
    if type(change_data) != dict:
        change_data = json.loads(change_data)
    return changeClass(**change_data)


# Hacky, but works for now.  Whatever we decide here, we probably need to expose it
# for those working with permissions so they're not having to get the strings
# correct every time.
def old_create_change_object(change_type, change_data):

    from concord.resources.state_changes import (AddItemResourceStateChange, RemoveItemResourceStateChange,
        ChangeResourceNameStateChange)
    from concord.permission_resources.state_changes import (AddPermissionStateChange, RemovePermissionStateChange,
        AddActorToPermissionStateChange, RemoveActorFromPermissionStateChange, AddRoleToPermissionStateChange,
        RemoveRoleFromPermissionStateChange)
    from concord.conditionals.state_changes import (AddConditionStateChange, RemoveConditionStateChange,
        AddVoteStateChange, ApproveStateChange)
    from concord.communities.state_changes import (ChangeNameStateChange, AddGovernorStateChange,
        AddOwnerStateChange, AddGovernorRoleStateChange, AddOwnerRoleStateChange,
        AddRoleStateChange, RemoveRoleStateChange, AddPeopleToRoleStateChange, 
        RemovePeopleFromRoleStateChange)

    state_changes_dict = {
        "resource_additem": AddItemResourceStateChange, 
        "resource_removeitem": RemoveItemResourceStateChange,
        "resource_changename": ChangeResourceNameStateChange,
        "permissionitem_addpermission": AddPermissionStateChange, 
        "permissionitem_removepermission": RemovePermissionStateChange,
        "permissionitem_addactortopermission": AddActorToPermissionStateChange,
        "permissionitem_removeactorfrompermission": RemoveActorFromPermissionStateChange,
        "permissionitem_addroletopermission": AddRoleToPermissionStateChange,
        "permissionitem_removerolefrompermission": RemoveRoleFromPermissionStateChange,
        "conditionalvote_addvote": AddVoteStateChange,
        "conditional_addcondition": AddConditionStateChange,
        "conditional_removecondition": RemoveConditionStateChange,
        "conditional_approvecondition": ApproveStateChange,
        "community_changename": ChangeNameStateChange,
        "community_addgovernor": AddGovernorStateChange,
        "community_addowner": AddOwnerStateChange,
        "community_addgovernorrole": AddGovernorRoleStateChange,
        "community_addownerrole": AddOwnerRoleStateChange,
        "community_addrole": AddRoleStateChange,
        "community_removerole": RemoveRoleStateChange,
        "community_addpeopletorole": AddPeopleToRoleStateChange,
        "community_removepeoplefromrole": RemovePeopleFromRoleStateChange,
        "base_ownerchange": ChangeOwnerStateChange,
        "base_enablefoundationalpermissionchange": EnableFoundationalPermissionStateChange,
        "base_disablefoundationalpermissionchange": DisableFoundationalPermissionStateChange
    }

    changeObject = state_changes_dict[change_type]
    if type(change_data) != dict:
        change_data = json.loads(change_data)
    
    return changeObject(**change_data)







