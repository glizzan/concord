from actions.state_changes import BaseStateChange

from permission_resources.models import PermissionsItem


#####################################
### Resource & Item State Changes ###
#####################################

class AddPermissionStateChange(BaseStateChange):
    name = "permissionresource_addpermission"

    def __init__(self, permission_type, permission_actor):
        self.permission_type = permission_type
        self.permission_actor = permission_actor

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        if actor and target and self.permission_type and self.permission_actor:
            return True
        return False

    def implement(self, actor, target):
        permission = PermissionsItem.objects.create(owner=actor,
            resource=target, actor=self.permission_actor, 
            action_type=self.permission_type)
        return permission


class RemovePermissionStateChange(BaseStateChange):
    name = "permissionresource_removepermission"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        if actor and target and self.item_pk:
            return True
        return False

    def implement(self, actor, target):
        try:
            item = PermissionsItem.objects.get(pk=self.item_pk)
            item.delete()
            return True
        except Exception as exception:
            print(exception)
            return False