# TODO: make these explicit abstract class and subclasses *have* to implement validate and
# implement

# TODO: I think there should be a good way to do the check caller here, so that when
# implementing this system a model can check that it's being called via a subclass of 
# this object, which is the only way for models to change I believe.


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
        return vars(self)



# Hacky, but works for now.  Whatever we decide here, we probably need to expose it
# for those working with permissions so they're not having to get the strings
# correct every time.
def create_change_object(change_type, change_data):
    from resources.state_changes import AddItemResourceStateChange, RemoveItemResourceStateChange
    from permission_resources.state_changes import AddPermissionStateChange, RemovePermissionStateChange
    state_changes_dict = {
        "resource_additem": AddItemResourceStateChange, 
        "resource_removeitem": RemoveItemResourceStateChange,
        "permissionresource_addpermission": AddPermissionStateChange, 
        "permissionresource_removepermission": RemovePermissionStateChange
    }
    changeObject = state_changes_dict[change_type]
    return changeObject(**change_data)







