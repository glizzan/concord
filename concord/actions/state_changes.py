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
        return self.name

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



# Hacky, but works for now.  Whatever we decide here, we probably need to expose it
# for those working with permissions so they're not having to get the strings
# correct every time.
def create_change_object(change_type, change_data):

    from resources.state_changes import (AddItemResourceStateChange, RemoveItemResourceStateChange,
        ChangeResourceNameStateChange)
    from permission_resources.state_changes import AddPermissionStateChange, RemovePermissionStateChange
    from conditionals.state_changes import (AddConditionStateChange, RemoveConditionStateChange,
        AddVoteStateChange, ApproveStateChange)
    from communities.state_changes import ChangeNameStateChange

    state_changes_dict = {
        "resource_additem": AddItemResourceStateChange, 
        "resource_removeitem": RemoveItemResourceStateChange,
        "resource_changename": ChangeResourceNameStateChange,
        "permissionresource_addpermission": AddPermissionStateChange, 
        "permissionresource_removepermission": RemovePermissionStateChange,
        "conditionalvote_addvote": AddVoteStateChange,
        "conditional_addcondition": AddConditionStateChange,
        "conditional_removecondition": RemoveConditionStateChange,
        "conditional_approvecondition": ApproveStateChange,
        "community_changename": ChangeNameStateChange,
        "base_ownerchange": ChangeOwnerStateChange
    }

    changeObject = state_changes_dict[change_type]
    if type(change_data) != dict:
        change_data = json.loads(change_data)
    
    return changeObject(**change_data)







