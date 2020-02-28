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

    def __init__(self, permission_type, permission_actors, permission_roles, 
        permission_configuration, inverse=False):
        """Permission actors and permission role pairs MUST be a list of zero or more
        strings."""
        self.permission_type = permission_type
        self.permission_actors = permission_actors if permission_actors else []
        self.permission_roles = permission_roles if permission_roles else []
        self.permission_configuration = permission_configuration
        self.inverse = inverse

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        from concord.resources.models import Resource, Item
        return [Community, Resource, Item]    

    def description_present_tense(self):
        permission_string = "add permission of type %s" % (self.permission_type)
        if self.permission_configuration:
            permission_string += " (configuration: %s)" % (str(self.permission_configuration))
        return permission_string

    def description_past_tense(self):
        permission_string = "added permission of type %s" % (self.permission_type)
        if self.permission_configuration:
            permission_string += " (configuration: %s)" % (str(self.permission_configuration))
        return permission_string

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        permission = PermissionsItem()
        permission.owner = target.get_owner() # FIXME: should it be the target owner though?
        permission.permitted_object = target
        permission.change_type = self.permission_type
        permission.inverse = self.inverse   
        if self.permission_actors:  # FIXME: maybe don't need to check if empty here
            permission.actors.add_actors(actors=self.permission_actors)
        permission.roles.add_roles(role_list=self.permission_roles)
        if self.permission_configuration:
            #FIXME: probably not the place to do this formatting :/
            configuration_dict = {}
            for key, value in self.permission_configuration.items():
                if value not in [None, [], ""]:
                    configuration_dict[key] = value
            permission.set_configuration(configuration_dict=configuration_dict)
        permission.save()
        return permission


class RemovePermissionStateChange(PermissionResourceBaseStateChange):
    description = "Remove permission"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        from concord.resources.models import Resource, Item
        return [Community, Resource, Item]    

    def description_present_tense(self):
        return "remove permission %d" % (self.item_pk)  

    def description_past_tense(self):
        return "removed permission %d" % (self.item_pk)

    def validate(self, actor, target):
        """
        put real logic here
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
    instantiated_fields = ['permission']

    def __init__(self, *, actor_to_add: str, permission_pk: int):
        self.actor_to_add = actor_to_add
        self.permission_pk = permission_pk

    def instantiate_fields(self):
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

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.actors.add_actors(actors=[self.actor_to_add])
        self.permission.save()
        return self.permission


class RemoveActorFromPermissionStateChange(PermissionResourceBaseStateChange):

    description = "Remove actor from permission"
    instantiated_fields = ['permission']

    def __init__(self, *, actor_to_remove: str, permission_pk: int):
        self.actor_to_remove = actor_to_remove
        self.permission_pk = permission_pk
        self.permission = self.look_up_permission()

    def instantiate_fields(self):
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

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.actors.remove_actors(actors=[self.actor_to_remove])
        self.permission.save()
        return self.permission


class AddRoleToPermissionStateChange(PermissionResourceBaseStateChange):

    description = "Add role to permission"
    instantiated_fields = ['permission']

    def __init__(self, *, role_name: str, permission_pk: int):
        self.role_name = role_name
        self.permission_pk = permission_pk

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        return "add role %s to permission %d (%s)" % (self.role_name, 
            self.permission_pk, self.permission.short_change_type())  

    def description_past_tense(self):
        return "added role %s to permission %d (%s)" % (self.role_name, 
            self.permission_pk, self.permission.short_change_type())

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.add_role_to_permission(role=self.role_name)
        self.permission.save()
        return self.permission


class RemoveRoleFromPermissionStateChange(PermissionResourceBaseStateChange):

    description = "Remove role from permission"
    instantiated_fields = ['permission']

    def __init__(self, *, role_name: str, permission_pk: int):
        self.role_name = role_name
        self.permission_pk = permission_pk

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]   

    @classmethod 
    def get_configurable_fields(self):
        return ["role_name"]

    @classmethod
    def get_uninstantiated_description(self, **configuration_kwargs):
        """Takes in an arbitrary number of configuration kwargs and uses them to 
        create a description.  Does not reference fields passed on init."""
        role_name = configuration_kwargs.get("role_name", " ")
        return "remove role%sfrom permission" % (role_name)

    def description_present_tense(self):
        return "remove role %s from permission %d (%s)" % (self.role_name, 
            self.permission_pk, self.permission.short_change_type())  

    def description_past_tense(self):
        return "removed role %s from permission %d (%s)" % (self.role_name, 
            self.permission_pk, self.permission.short_change_type())  

    def check_configuration(self, permission):
        '''All configurations must pass for the configuration check to pass.'''
        self.instantiate_fields()
        configuration = permission.get_configuration()
        if "role_name" in configuration:  
            if self.role_name not in configuration["role_name"]:
                return False
        return True

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.remove_role_from_permission(role=self.role_name)
        self.permission.save()
        return self.permission


class ChangePermissionConfigurationStateChange(PermissionResourceBaseStateChange):

    description = "Change configuration of permission"
    instantiated_fields = ['permission']

    def __init__(self, *, configurable_field_name: str, configurable_field_value: str, 
        permission_pk: int):
        self.configurable_field_name = configurable_field_name
        self.configurable_field_value = configurable_field_value
        self.permission_pk = permission_pk

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        return "change configuration field %s to value %s on permission %d (%s)" % (self.configurable_field_name,
            self.configurable_field_value, self.permission_pk, self.permission.short_change_type())
    
    def description_past_tense(self):
        return "changed configuration field %s to value %s on permission %d (%s)" % (self.configurable_field_name,
            self.configurable_field_value, self.permission_pk, self.permission.short_change_type())

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target):
        self.instantiate_fields()
        configuration = self.permission.get_configuration()
        # FIXME: might there be problems with formatting of configurable field value? like, how is a 
        # list of role names formatted?
        configuration[self.configurable_field_name] = self.configurable_field_value
        self.permission.set_configuration(configuration)
        self.permission.save()
        return self.permission


# FIXME:  Might just be a configurable field?
class ChangeInverseStateChange(PermissionResourceBaseStateChange):

    description = "Toggle permission's inverse field"
    instantiated_fields = ['permission']

    def __init__(self, *, change_to: bool, permission_pk: int):
        self.change_to = change_to
        self.permission_pk = permission_pk
    
    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_allowable_targets(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        return "change inverse field to value %s on permission %d (%s)" % (self.change_to, 
            self.permission_pk, self.permission.short_change_type())
    
    def description_past_tense(self):
        return "changed inverse field to value %s on permission %d (%s)" % (self.change_to, 
            self.permission_pk, self.permission.short_change_type())

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target):
        self.instantiate_fields()
        self.permission.inverse = self.change_to
        self.permission.save()
        return self.permission