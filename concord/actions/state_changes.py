import json, warnings

from django.contrib.contenttypes.models import ContentType


class BaseStateChange(object):

    allowable_targets = []
    instantiated_fields = []

    @classmethod 
    def get_change_type(cls):
        return cls.__module__ + "." + cls.__name__

    @classmethod 
    def get_allowable_targets(cls):
        return cls.allowable_targets

    @classmethod 
    def get_configurable_fields(self):
        if hasattr(self, 'check_configuration'): 
            warnings.warn("You have added a check_configuration method to your state change without specifying any configurable fields.")
        return []

    def instantiate_fields(self):
        '''Helper method used by state change subclasses that have fields which require database
        lookups.  Not called by default, to prevent unnecessary db queries.'''
        return False

    def validate(self, actor, target):
        ...

    def implement(self, actor, target):
        ...

    def get_change_data(self):
        '''
        Given the python Change object, generates a json list of field names
        and values.  Does not include instantiated fields.
        '''
        new_vars = vars(self)
        for field in self.instantiated_fields:
            if field in new_vars:
                del(new_vars)[field]
        return json.dumps(new_vars)


class ChangeOwnerStateChange(BaseStateChange):
    description = "Change owner"

    def __init__(self, new_owner_content_type, new_owner_id):
        self.new_owner_content_type = new_owner_content_type
        self.new_owner_id = new_owner_id

    @classmethod
    def get_allowable_targets(cls):
        '''
        Gets all models in registered apps and returns them if they have a foundational
        permission enabled attribute (a bit of a hack to find anything descended from
        PermissionedModel) and if they are not abstract models.
        '''
        from django.apps import apps
        models = apps.get_models()
        allowable_targets = []
        for model in models:
            if hasattr(model, "foundational_permission_enabled") and not model._meta.abstract:
                allowable_targets.append(model)  
        return allowable_targets  

    def description_present_tense(self):
        return "change owner of community to %s" % (self.new_owner)  

    def description_past_tense(self):
        return "changed owner of community to %s" % (self.new_owner) 

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target):

        # Given the content type and ID, instantiate owner
        ct = ContentType.objects.get_for_id(self.new_owner_content_type)
        model_class = ct.model_class()
        new_owner = model_class.objects.get(id=self.new_owner_id)

        target.owner = new_owner
        target.save()
        return target


class EnableFoundationalPermissionStateChange(BaseStateChange):
    description = "Enable the foundational permission"

    @classmethod
    def get_allowable_targets(cls):
        '''
        Gets all models in registered apps and returns them if they have a foundational
        permission enabled attribute (a bit of a hack to find anything descended from
        PermissionedModel) and if they are not abstract models.
        '''
        from django.apps import apps
        models = apps.get_models()
        allowable_targets = []
        for model in models:
            if hasattr(model, "foundational_permission_enabled") and not model._meta.abstract:
                allowable_targets.append(model)  
        return allowable_targets  

    def description_present_tense(self):
        return "enable foundational permission" 

    def description_past_tense(self):
        return "enabled foundational permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target):
        target.foundational_permission_enabled = True
        target.save()
        return target


class DisableFoundationalPermissionStateChange(BaseStateChange):
    description = "disable foundational permission"

    @classmethod
    def get_allowable_targets(cls):
        '''
        Gets all models in registered apps and returns them if they have a foundational
        permission enabled attribute (a bit of a hack to find anything descended from
        PermissionedModel) and if they are not abstract models.
        '''
        from django.apps import apps
        models = apps.get_models()
        allowable_targets = []
        for model in models:
            if hasattr(model, "foundational_permission_enabled") and not model._meta.abstract:
                allowable_targets.append(model)  
        return allowable_targets  

    def description_present_tense(self):
        return "disable foundational permission" 

    def description_past_tense(self):
        return "disabled foundational permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target):
        target.foundational_permission_enabled = False
        target.save()
        return target

class EnableGoverningPermissionStateChange(BaseStateChange):
    description = "Enable the governing permission"

    @classmethod
    def get_allowable_targets(cls):
        '''
        Gets all models in registered apps and returns them if they have a foundational
        permission enabled attribute (a bit of a hack to find anything descended from
        PermissionedModel) and if they are not abstract models.

        # NOTE: although this is for enabling governing permissions, the same hack works
        '''
        from django.apps import apps
        models = apps.get_models()
        allowable_targets = []
        for model in models:
            if hasattr(model, "foundational_permission_enabled") and not model._meta.abstract:
                allowable_targets.append(model)  
        return allowable_targets  

    def description_present_tense(self):
        return "enable governing permission" 

    def description_past_tense(self):
        return "enabled governing permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target):
        target.governing_permission_enabled = True
        target.save()
        return target


class DisableGoverningPermissionStateChange(BaseStateChange):
    description = "disable governing permission"

    @classmethod
    def get_allowable_targets(cls):
        '''
        Gets all models in registered apps and returns them if they have a foundational
        permission enabled attribute (a bit of a hack to find anything descended from
        PermissionedModel) and if they are not abstract models.

        Same hack works as for DisableFoundationalPermissionStateChange.
        '''
        from django.apps import apps
        models = apps.get_models()
        allowable_targets = []
        for model in models:
            if hasattr(model, "foundational_permission_enabled") and not model._meta.abstract:
                allowable_targets.append(model)  
        return allowable_targets  

    def description_present_tense(self):
        return "disable governing permission" 

    def description_past_tense(self):
        return "disabled governing permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target):
        target.governing_permission_enabled = False
        target.save()
        return target


# FIXME: must be a better approach than just listing these
def foundational_changes():
    return [
        'concord.communities.state_changes.AddGovernorStateChange',
        'concord.communities.state_changes.AddOwnerStateChange',
        'concord.communities.state_changes.RemoveGovernorStateChange',
        'concord.communities.state_changes.RemoveOwnerStateChange',
        'concord.communities.state_changes.AddGovernorRoleStateChange',
        'concord.communities.state_changes.AddOwnerRoleStateChange',
        'concord.communities.state_changes.RemoveGovernorRoleStateChange',
        'concord.communities.state_changes.RemoveOwnerRoleStateChange',
        'concord.actions.state_changes.EnableFoundationalPermissionStateChange',
        'concord.actions.state_changes.DisableFoundationalPermissionStateChange',
        'concord.actions.state_changes.EnableGoverningPermissionStateChange',
        'concord.actions.state_changes.DisableGoverningPermissionStateChange'
    ]


class Changes(object):
    '''Helper object which lets developers easily access change types.'''

    class Actions(object):

        ChangeOwner = 'concord.actions.state_changes.ChangeOwnerStateChange'
        EnableFoundationalPermission = 'concord.actions.state_changes.EnableFoundationalPermissionStateChange'
        DisableFoundationalPermission = 'concord.actions.state_changes.DisableFoundationalPermissionStateChange'
        EnableGoverningPermission = 'concord.actions.state_changes.EnableGoverningPermissionStateChange'
        DisableGoverningPermission = 'concord.actions.state_changes.DisableGoverningPermissionStateChange'

    class Communities(object):

        ChangeName = 'concord.communities.state_changes.ChangeNameStateChange'
        AddMember = 'concord.communities.state_changes.AddMemberStateChange'
        AddMembers = 'concord.communities.state_changes.AddMembersStateChange'
        RemoveMember = 'concord.communities.state_changes.RemoveMemberStateChange'
        RemoveMembers = 'concord.communities.state_changes.RemoveMembersStateChange'
        AddGovernor = 'concord.communities.state_changes.AddGovernorStateChange'
        RemoveGovernor = 'concord.communities.state_changes.RemoveGovernorStateChange'
        AddGovernorRole = 'concord.communities.state_changes.AddGovernorRoleStateChange'
        RemoveGovernorRole = 'concord.communities.state_changes.RemoveGovernorRoleStateChange'
        AddOwner = 'concord.communities.state_changes.AddOwnerStateChange'
        RemoveOwner = 'concord.communities.state_changes.RemoveOwnerStateChange'
        AddOwnerRole = 'concord.communities.state_changes.AddOwnerRoleStateChange'
        RemoveOwnerRole = 'concord.communities.state_changes.RemoveOwnerRoleStateChange'
        AddRole = 'concord.communities.state_changes.AddRoleStateChange'
        RemoveRole = 'concord.communities.state_changes.RemoveRoleStateChange'
        AddPeopleToRole = 'concord.communities.state_changes.AddPeopleToRoleStateChange'
        RemovePeopleFromRole = 'concord.communities.state_changes.RemovePeopleFromRoleStateChange'

    class Conditionals(object):

        AddCondition = 'concord.conditionals.state_changes.AddConditionStateChange'
        RemoveCondition = 'concord.conditionals.state_changes.RemoveConditionStateChange'
        ChangeCondition = 'concord.conditionals.state_changes.ChangeConditionStateChange'
        AddVote = 'concord.conditionals.state_changes.AddVoteStateChange'
        Approve = 'concord.conditionals.state_changes.ApproveStateChange'
        Reject = 'concord.conditionals.state_changes.RejectStateChange'

    class Permissions(object):

        AddPermission = 'concord.permission_resources.state_changes.AddPermissionStateChange'        
        RemovePermission = 'concord.permission_resources.state_changes.RemovePermissionStateChange'        
        AddActorToPermission = 'concord.permission_resources.state_changes.AddActorToPermissionStateChange'        
        RemoveActorFromPermission = 'concord.permission_resources.state_changes.RemoveActorFromPermissionStateChange'        
        AddRoleToPermission = 'concord.permission_resources.state_changes.AddRoleToPermissionStateChange'        
        RemoveRoleFromPermission = 'concord.permission_resources.state_changes.RemoveRoleFromPermissionStateChange'        
        ChangePermissionConfiguration = 'concord.permission_resources.state_changes.ChangePermissionConfigurationStateChange'        
        
    class Resources(object):
        
        ChangeResourceName = 'concord.resources.state_changes.ChangeResourceNameStateChange'        
        AddItem = 'concord.resources.state_changes.AddItemResourceStateChange'  #Remove 'Resource'?  
        RemoveItem = 'concord.resources.state_changes.RemoveItemResourceStateChange'  # Remove 'Resource'?        
        
        
    





