import json

from actions.state_changes import BaseStateChange
from permission_resources.models import PermissionsItem


#####################################
### Resource & Item State Changes ###
#####################################

class AddPermissionStateChange(BaseStateChange):
    name = "permissionitem_addpermission"

    def __init__(self, permission_type, permission_actor, permission_role):
        self.permission_type = permission_type
        self.permission_actor = permission_actor
        self.permission_role = permission_role

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        permission = PermissionsItem()
        permission.owner = actor # Do we care about owner type here?
        permission.permitted_object = target
        permission.change_type = self.permission_type
        if self.permission_actor:
            permission.actors = json.dumps([self.permission_actor])
        if self.permission_role:
            permission.roles = json.dumps([self.permission_role])
        permission.save()
        return permission


class RemovePermissionStateChange(BaseStateChange):
    name = "permissionitem_removepermission"

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


class AddActorToPermissionStateChange(BaseStateChange):
    name = "permissionitem_addactortopermission"

    def __init__(self, actor_to_be_added):
        self.actor_to_be_added = actor_to_be_added
    
    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.target.add_actor_to_permission(self.actor_to_be_added)
        self.target.save()
        return target


class RemoveActorFromPermissionStateChange(BaseStateChange):
    name = "permissionitem_removeactorfrompermission"

    def __init__(self, actor_to_be_removed):
        self.actor_to_be_removed = actor_to_be_removed
    
    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.target.remove_actor_from_permission(self.actor_to_be_removed)
        self.target.save()
        return target


class AddRoleToPermissionStateChange(BaseStateChange):
    name = "permissionitem_addroletopermission"

    def __init__(self, role_name, community_pk):
        self.role_name = role_name
        self.community_pk = community_pk
    
    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.target.add_role_to_permission(self.role_name, self.community_pk)
        self.target.save()
        return target


class RemoveRoleFromPermissionStateChange(BaseStateChange):
    name = "permissionitem_removerolefrompermission"

    def __init__(self, role_name, community_pk):
        self.role_name = role_name
        self.community_pk = community_pk
    
    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.target.remove_role_from_permission(self.role_name, self.community_pk)
        self.target.save()
        return target