import json

from concord.actions.state_changes import BaseStateChange
from concord.permission_resources.models import PermissionsItem


#####################################
### Resource & Item State Changes ###
#####################################

class PermissionResourceBaseStateChange(BaseStateChange):

    def look_up_permission(self):
        return PermissionsItem.objects.get(pk=self.permission_pk)


class AddPermissionStateChange(PermissionResourceBaseStateChange):
    description = "Add permission"

    def __init__(self, permission_type, permission_actors, permission_role_pairs):
        """Permission actors and permission role pairs MUST be a list of zero or more
        strings."""
        self.permission_type = permission_type
        self.permission_actors = permission_actors if permission_actors else []
        self.permission_role_pairs = permission_role_pairs if permission_role_pairs else []

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        from concord.resources.models import Resource, Item
        return [Community, SubCommunity, SuperCommunity, Resource, Item]    

    def description_present_tense(self):
        return "add permission of type %s" % (self.permission_type)

    def description_past_tense(self):
        return "added permission of type %s" % (self.permission_type)

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
        for actor in self.permission_actors:
            if actor:
                permission.add_actor_to_permission(actor=actor)
        for role_pair in self.permission_role_pairs:
            if role_pair:
                permission.add_role_pair_to_permission(role_pair_to_add=role_pair)
        permission.save()
        return permission


class RemovePermissionStateChange(PermissionResourceBaseStateChange):
    description = "Remove permission"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        from concord.resources.models import Resource, Item
        return [Community, SubCommunity, SuperCommunity, Resource, Item]    

    def description_present_tense(self):
        return "remove permission %d" % (self.item_pk)  

    def description_past_tense(self):
        return "removed permission %d" % (self.item_pk)

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


class AddActorToPermissionStateChange(PermissionResourceBaseStateChange):
    description = "Add actor to permission"

    def __init__(self, *, actor_to_add: str, permission_pk: int):
        self.actor_to_add = actor_to_add
        self.permission_pk = permission_pk
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    def description_present_tense(self):
        return "add actor %s to permission %d (%s)" % (self.actor_to_add, 
            self.permission_pk, self.permission.short_change_type())  

    def description_past_tense(self):
        return "added actor %s to permission %d (%s)" % (self.actor_to_add, 
            self.permission_pk, self.permission.short_change_type()) 

    def get_change_data(self):
        # TODO: make permission a custom field so we don't need to override get_change_data
        '''
        Given the python Change object, generates a json list of field names
        and values.
        '''
        new_vars = vars(self)
        del(new_vars)["permission"]
        return json.dumps(new_vars)

    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.permission.add_actor_to_permission(actor=self.actor_to_add)
        self.permission.save()
        return self.permission


class RemoveActorFromPermissionStateChange(PermissionResourceBaseStateChange):
    description = "Remove actor from permission"

    def __init__(self, *, actor_to_remove: str, permission_pk: int):
        self.actor_to_remove = actor_to_remove
        self.permission_pk = permission_pk
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]

    def description_present_tense(self):
        return "remove actor %s from permission %d (%s) " % (self.actor_to_remove, 
            self.permission_pk, self.permission.short_change_type())  

    def description_past_tense(self):
        return "removed actor %s from permission %d (%s)" % (self.actor_to_remove, 
            self.permission_pk, self.permission.short_change_type())   

    def get_change_data(self):
        # TODO: make permission a custom field so we don't need to override get_change_data
        '''
        Given the python Change object, generates a json list of field names
        and values.
        '''
        new_vars = vars(self)
        del(new_vars)["permission"]
        return json.dumps(new_vars)

    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.permission.remove_actor_from_permission(actor=self.actor_to_remove)
        self.permission.save()
        return self.permission


class AddRoleToPermissionStateChange(PermissionResourceBaseStateChange):
    description = "Add role to permission"

    def __init__(self, *, role_name: str, community_pk: int, permission_pk: int):
        self.role_name = role_name
        self.community_pk = community_pk
        self.permission_pk = permission_pk
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        return "add role %s (community %d) to permission %d (%s)" % (self.role_name, 
            self.community_pk, self.permission_pk, self.permission.short_change_type())  

    def description_past_tense(self):
        return "added role %s (community %d) to permission %d (%s)" % (self.role_name, 
            self.community_pk, self.permission_pk, self.permission.short_change_type())

    def get_change_data(self):
        # TODO: make permission a custom field so we don't need to override get_change_data
        '''
        Given the python Change object, generates a json list of field names
        and values.
        '''
        new_vars = vars(self)
        del(new_vars)["permission"]
        return json.dumps(new_vars)

    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.permission.add_role_to_permission(role=self.role_name, 
            community=str(self.community_pk))
        self.permission.save()
        return self.permission


class RemoveRoleFromPermissionStateChange(PermissionResourceBaseStateChange):
    description = "Remove role from permission"

    def __init__(self, *, role_name: str, community_pk: int, permission_pk: int):
        self.role_name = role_name
        self.community_pk = community_pk
        self.permission_pk = permission_pk
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        return "remove role %s (community %d) from permission %d (%s)" % (self.role_name, 
            self.community_pk, self.permission_pk, self.permission.short_change_type())  

    def description_past_tense(self):
        return "removed role %s (community %d) from permission %d (%s)" % (self.role_name, 
            self.community_pk, self.permission_pk, self.permission.short_change_type())  

    def get_change_data(self):
        # TODO: make permission a custom field so we don't need to override get_change_data
        '''
        Given the python Change object, generates a json list of field names
        and values.
        '''
        new_vars = vars(self)
        del(new_vars)["permission"]
        return json.dumps(new_vars)

    def validate(self, actor, target):
        # TODO: put real logic here
        return True
    
    def implement(self, actor, target):
        self.permission.remove_role_from_permission(role=self.role_name,
            community=str(self.community_pk))
        self.permission.save()
        return self.permission