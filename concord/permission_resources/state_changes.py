import json

from django.core.exceptions import ValidationError

from concord.actions.state_changes import BaseStateChange
from concord.permission_resources.models import PermissionsItem
from concord.permission_resources.utils import get_verb_given_permission_type
from concord.actions import text_utils


################################
### Permission State Changes ###
################################

class PermissionResourceBaseStateChange(BaseStateChange):
    instantiated_fields = ['permission']

    def look_up_permission(self):
        return PermissionsItem.objects.get(pk=self.permission_pk)


class AddPermissionStateChange(PermissionResourceBaseStateChange):
    description = "Add permission"

    def __init__(self, permission_type, permission_actors, permission_roles, 
        permission_configuration, anyone=False, inverse=False):
        """Permission actors and permission role pairs MUST be a list of zero or more
        strings."""
        self.permission_type = permission_type
        self.permission_actors = permission_actors if permission_actors else []
        self.permission_roles = permission_roles if permission_roles else []
        self.permission_configuration = permission_configuration
        self.inverse = inverse
        self.anyone = anyone

    @classmethod
    def get_settable_classes(cls):
        from concord.communities.models import Community
        from concord.resources.models import Resource, Item
        return [Community, Resource, Item, PermissionsItem]    

    def description_present_tense(self):        
        permission_string = "add permission '%s'" % get_verb_given_permission_type(self.permission_type)
        if self.permission_configuration:
            permission_string += " (configuration: %s)" % (str(self.permission_configuration))
        return permission_string

    def description_past_tense(self):
        permission_string = "added permission '%s'" % get_verb_given_permission_type(self.permission_type)
        if self.permission_configuration:
            permission_string += " (configuration: %s)" % (str(self.permission_configuration))
        return permission_string

    def validate(self, actor, target):
        """ To validate a permission being added, we need to instantiate the permission and check its configuration is valid.
        We also need to validate that the given permission can be set on the target.
        """
        from concord.actions.utils import get_state_change_object_given_name
        permission =  get_state_change_object_given_name(self.permission_type)

        # check that target is a valid class for the permission to be set on
        if target.__class__ not in permission.get_settable_classes():
            self.set_validation_error("This kind of permission cannot be set on target %s of class %s, must be %s" % (
                str(target), str(target.__class__), ", ".join([str(option) for option in permission.get_settable_classes()])))
            return False

        # check configuration
        if hasattr(permission, "check_configuration") and self.permission_configuration is not None: 
            is_valid, error_message = permission.check_configuration_is_valid(self.permission_configuration)
            if not is_valid:
                self.set_validation_error(error_message)
                return False

        return True

    def implement(self, actor, target, save=True):

        permission = PermissionsItem()
        permission.owner = target.get_owner() # FIXME: should it be the target owner though?
        permission.permitted_object = target
        permission.anyone = self.anyone
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
    
        if save:
            permission.save()
    
        return permission


class RemovePermissionStateChange(PermissionResourceBaseStateChange):
    description = "Remove permission"
    preposition = "from"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    @classmethod
    def get_settable_classes(cls):
        from concord.communities.models import Community
        from concord.resources.models import Resource, Item
        return [Community, Resource, Item]    

    def description_present_tense(self):
        return "remove permission with id %d" % (self.item_pk)  

    def description_past_tense(self):
        return "removed permission with id %d" % (self.item_pk)

    def validate(self, actor, target):
        """
        put real logic here
        """
        if actor and target and self.item_pk:
            return True
        self.set_validation_error("Must supply item_pk")
        return False

    def implement(self, actor, target, save=True):
        try:
            item = PermissionsItem.objects.get(pk=self.item_pk)
            if save:
                item.delete()
            return True
        except Exception as exception:
            print(exception)
            return False


class AddActorToPermissionStateChange(PermissionResourceBaseStateChange):

    description = "Add actor to permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, actor_to_add: str, permission_pk: int):
        self.actor_to_add = actor_to_add
        self.permission_pk = permission_pk

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]

    def description_present_tense(self):
        if hasattr(self, "permission"):
            return "add actor %s to permission %d (%s)" % (self.actor_to_add, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "add actor %s to permission %d" % (self.actor_to_add, self.permission_pk) 

    def description_past_tense(self):
        if hasattr(self, "permission"):
            return "added actor %s to permission %d (%s)" % (self.actor_to_add, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "added actor %s to permission %d" % (self.actor_to_add, self.permission_pk)


    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):
        
        self.instantiate_fields()
        self.permission.actors.add_actors(actors=[self.actor_to_add])

        if save:
            self.permission.save()
    
        return self.permission


class RemoveActorFromPermissionStateChange(PermissionResourceBaseStateChange):

    description = "Remove actor from permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, actor_to_remove: str, permission_pk: int):
        self.actor_to_remove = actor_to_remove
        self.permission_pk = permission_pk
        self.permission = self.look_up_permission()

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]

    def description_present_tense(self):
        if hasattr(self, "permission"):
            return "remove actor %s from permission %d (%s)" % (self.actor_to_remove, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "remove actor %s from permission %d" % (self.actor_to_remove, self.permission_pk) 

    def description_past_tense(self):
        if hasattr(self, "permission"):
            return "removed actor %s from permission %d (%s)" % (self.actor_to_remove, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "removed actor %s from permission %d" % (self.actor_to_remove, self.permission_pk)

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):

        self.instantiate_fields()
        self.permission.actors.remove_actors(actors=[self.actor_to_remove])
        
        if save:
            self.permission.save()
        
        return self.permission


class AddRoleToPermissionStateChange(PermissionResourceBaseStateChange):

    description = "Add role to permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, role_name: str, permission_pk: int):
        self.role_name = role_name
        self.permission_pk = permission_pk

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        if hasattr(self, "permission"):
            return "add role %s to permission %d (%s)" % (self.role_name, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "add role %s to permission %d" % (self.role_name, self.permission_pk) 

    def description_past_tense(self):
        if hasattr(self, "permission"):
            return "added role %s to permission %d (%s)" % (self.role_name, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "added role %s to permission %d" % (self.role_name, self.permission_pk)

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):

        self.instantiate_fields()
        self.permission.add_role_to_permission(role=self.role_name)
        
        if save:
            self.permission.save()
        
        return self.permission


class RemoveRoleFromPermissionStateChange(PermissionResourceBaseStateChange):

    description = "Remove role from permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, role_name: str, permission_pk: int):
        self.role_name = role_name
        self.permission_pk = permission_pk

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]   

    @classmethod 
    def get_configurable_fields(self):
        return { "role_name": 
            { "display": "Role that can be removed from the permission", "type": "PermissionRoleField" } }

    @classmethod
    def get_uninstantiated_description(self, **configuration_kwargs):
        """Takes in an arbitrary number of configuration kwargs and uses them to 
        create a description.  Does not reference fields passed on init."""
        role_name = configuration_kwargs.get("role_name", " ")
        return "remove role%sfrom permission" % (role_name)

    def description_present_tense(self):
        if hasattr(self, "permission"):
            return "remove role %s from permission %d (%s)" % (self.role_name, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "remove role %s from permission %d" % (self.role_name, self.permission_pk) 

    def description_past_tense(self):
        if hasattr(self, "permission"):
            return "removed role %s from permission %d (%s)" % (self.role_name, self.permission_pk, 
                self.permission.get_change_type())
        else:
            return "removed role %s from permission %d" % (self.role_name, self.permission_pk)

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "role_name" in configuration:
            if type(configuration["role_name"]) != str:
                return False, "Role name must be sent as string, not " + str(type(configuration["role_name"]))
        return True, ""

    def check_configuration(self, action, permission):
        '''All configurations must pass for the configuration check to pass.'''
        self.instantiate_fields()
        configuration = permission.get_configuration()
        if "role_name" in configuration:  
            if self.role_name not in configuration["role_name"]:
                return False, "Can't remove role %s from permission, allowable fields are: %s" % (self.role_name,
                    ", ".join(configuration["role_name"]))
        return True, None

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):

        self.instantiate_fields()
        self.permission.remove_role_from_permission(role=self.role_name)
        
        if save:
            self.permission.save()
        
        return self.permission


class ChangePermissionConfigurationStateChange(PermissionResourceBaseStateChange):

    description = "Change configuration of permission"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, configurable_field_name: str, configurable_field_value: str, 
        permission_pk: int):
        self.configurable_field_name = configurable_field_name
        self.configurable_field_value = configurable_field_value
        self.permission_pk = permission_pk

    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        return "change configuration field %s to value %s on permission %d (%s)" % (self.configurable_field_name,
            self.configurable_field_value, self.permission_pk, self.permission.get_change_type())
    
    def description_past_tense(self):
        return "changed configuration field %s to value %s on permission %d (%s)" % (self.configurable_field_name,
            self.configurable_field_value, self.permission_pk, self.permission.get_change_type())

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):

        self.instantiate_fields()
        configuration = self.permission.get_configuration()
        # FIXME: might there be problems with formatting of configurable field value? like, how is a 
        # list of role names formatted?
        configuration[self.configurable_field_name] = self.configurable_field_value
        self.permission.set_configuration(configuration)
        
        if save:
            self.permission.save()
        
        return self.permission


# FIXME:  Might just be a configurable field?
class ChangeInverseStateChange(PermissionResourceBaseStateChange):

    description = "Toggle permission's inverse field"
    preposition = "for"
    instantiated_fields = ['permission']

    def __init__(self, *, change_to: bool, permission_pk: int):
        self.change_to = change_to
        self.permission_pk = permission_pk
    
    def instantiate_fields(self):
        self.permission = self.look_up_permission()

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]   

    def description_present_tense(self):
        return "change inverse field to value %s on permission %d (%s)" % (self.change_to, 
            self.permission_pk, self.permission.get_change_type())
    
    def description_past_tense(self):
        return "changed inverse field to value %s on permission %d (%s)" % (self.change_to, 
            self.permission_pk, self.permission.get_change_type())

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):

        self.instantiate_fields()
        self.permission.inverse = self.change_to
        
        if save:
            self.permission.save()
        
        return self.permission


class EnableAnyoneStateChange(PermissionResourceBaseStateChange):

    description = "Give anyone permission"
    preposition = "for"

    def __init__(self, *, permission_pk: int):
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]

    def description_present_tense(self):
        return f"give anyone permission {self.permission_pk}" 

    def description_past_tense(self):
        return f"gave anyone permission {self.permission_pk}" 

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):

        permission = self.look_up_permission()
        permission.anyone = True
        
        if save:
            permission.save()
        
        return permission


class DisableAnyoneStateChange(PermissionResourceBaseStateChange):

    description = "Remove anyone from permission"
    preposition = "for"

    def __init__(self, *, permission_pk: int):
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return [PermissionsItem]

    def description_present_tense(self):
        return f"remove anyone from permission {self.permission_pk}" 

    def description_past_tense(self):
        return f"removed anyone from permission {self.permission_pk}" 

    def validate(self, actor, target):
        # put real logic here
        return True
    
    def implement(self, actor, target, save=True):

        permission = self.look_up_permission()
        permission.anyone = False
        
        if save:
            permission.save()
        
        return permission


class AddPermissionConditionStateChange(PermissionResourceBaseStateChange):
    description = "Add condition"

    def __init__(self, *, permission_pk, condition_type, condition_data, permission_data):
        self.permission_pk = permission_pk
        self.condition_type = condition_type
        self.condition_data = condition_data
        self.permission_data = permission_data if permission_data else []

    @classmethod
    def get_settable_classes(cls):
        from concord.permission_resources.models import PermissionsItem
        return [PermissionsItem]

    def description_present_tense(self):
        return f"add condition {self.condition_type} to permission"   

    def description_past_tense(self):
        return f"added condition {self.condition_type} to permission"  

    def generate_mock_actions(self, actor, permission):
        """Helper method with template generation logic, since we're using it in both validate and implement.
        The actions below are stored within the template, and copied+instantiated when a separate action triggers 
        the permission to do so."""

        from concord.conditionals.client import ConditionalClient
        from concord.permission_resources.client import PermissionResourceClient

        cond_client = ConditionalClient(actor=actor)
        cond_client.mode = "mock"
        perm_client = PermissionResourceClient(actor=actor)   
        perm_client.mode = "mock"

        mock_action_list = []
        action_1 = cond_client.set_condition_on_action(condition_type=self.condition_type, 
            condition_data=self.condition_data, permission_pk=permission.pk)
        action_1.add_command_to_dependent_fields(command="REPLACE target WITH trigger_action")
        mock_action_list.append(action_1)

        perm_client.target = action_1
        for permission_item_data in self.permission_data:
            next_action = perm_client.add_permission(**permission_item_data)
            command = f"REPLACE target WITH previous_action {action_1.unique_id} result"
            next_action.add_command_to_dependent_fields(command=command)
            mock_action_list.append(next_action)
        
        return mock_action_list

    def validate(self, actor, target):
        permission = self.look_up_permission()
        try:
            mock_action_list = self.generate_mock_actions(actor, permission)    
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False
        
    def implement(self, actor, target, save=True):

        permission = self.look_up_permission() 
        
        permission.condition.action_list = self.generate_mock_actions(actor, permission)
        condition_action, permissions_actions = permission.condition.action_list[0], permission.condition.action_list[1:]
        permission.condition.description = text_utils.condition_template_to_text(condition_action, permissions_actions)
        
        if save:
            permission.save()

        return permission


class RemovePermissionConditionStateChange(PermissionResourceBaseStateChange):
    description = "Remove leadership condition"

    def __init__(self, *, permission_pk: int):
        self.permission_pk = permission_pk

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return f"remove condition from permission"   

    def description_past_tense(self):
        return f"removed condition from permission"  

    def validate(self, actor, target):
        return True
        
    def implement(self, actor, target, save=True):

        permission = self.look_up_permission()

        permission.condition.action_list = []
        
        if save:
            permission.save()

        return permission


##############################
### Template State Changes ###
##############################


class EditTemplateStateChange(BaseStateChange):
    description = "Edit Template"

    def __init__(self, template_object_id, field_name, new_field_data):
        self.template_object_id = template_object_id
        self.field_name = field_name
        self.new_field_data = new_field_data

    @classmethod
    def get_settable_classes(cls):
        from concord.permission_resources.models import Template
        return [Template]    

    def description_present_tense(self):
        permission_string = "edit template field %s to %s" % (self.field_name, self.new_field_data)
        return permission_string

    def description_past_tense(self):
        permission_string = "edited template field %s to %s" % (self.field_name, self.new_field_data)
        return permission_string

    def validate(self, actor, target):
        """
        put real logic here
        """
        result = target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        if result.__class__.__name__ == "ValidationError":
            self.set_validation_error(result.message)
            return False
        return True

    def implement(self, actor, target, save=True):

        target.data.update_field(self.template_object_id, self.field_name, self.new_field_data)
        
        if save:
            target.save()

        return target