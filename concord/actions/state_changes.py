import json

# TODO: make these explicit abstract class and subclasses *have* to implement validate and
# implement

# TODO: I think there should be a good way to do the check caller here, so that when
# implementing this system a model can check that it's being called via a subclass of 
# this object, which is the only way for models to change I believe.


class BaseStateChange(object):

    allowable_targets = []

    @classmethod 
    def get_change_type(cls):
        return cls.__module__ + "." + cls.__name__

    @classmethod 
    def get_allowable_targets(cls):
        return cls.allowable_targets

    def validate(self, actor, target):
        ...

    def implement(self, actor, target):
        ...

    def get_change_data(self):
        '''
        Given the python Change object, generates a json list of field names
        and values.
        '''
        return json.dumps(vars(self))


class ChangeOwnerStateChange(BaseStateChange):
    description = "Change owner"

    def __init__(self, new_owner, new_owner_type):
        # NOTE: new_owner SHOULD be the PK of the owner but for now it is their name
        self.new_owner = new_owner
        self.new_owner_type = new_owner_type

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
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        target.owner = self.new_owner
        target.owner_type = self.new_owner_type
        target.save()
        return target


class EnableFoundationalPermissionStateChange(BaseStateChange):
    description = "Enable the foundational permission"
    name = "base_enablefoundationalpermissionchange"

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
        TODO: put real logic here
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

