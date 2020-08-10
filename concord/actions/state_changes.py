import json, warnings

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.apps import apps


class BaseStateChange(object):

    allowable_targets = []
    settable_classes = []
    instantiated_fields = []
    is_foundational = False

    @classmethod 
    def get_change_type(cls):
        return cls.__module__ + "." + cls.__name__

    @classmethod 
    def get_allowable_targets(cls):
        """Returns the classes that an action of this type may target.  Most likely called by the validate
        method in a state change."""
        return cls.allowable_targets

    @classmethod 
    def get_settable_classes(cls):
        """Returns the classes that a permission with this change type may be set on.  This overlaps with
        allowable targets, but also includes classes that allowable targets may be nested on.  Most likely
        called by the validate method in AddPermissionStateChange."""
        return cls.settable_classes

    @classmethod
    def get_all_possible_targets(cls):
        """Gets all permissioned models in system that are not abstract."""
        from concord.actions.utils import get_all_permissioned_models
        return get_all_permissioned_models()

    @classmethod 
    def get_configurable_fields(cls):
        if hasattr(cls, 'check_configuration'): 
            warnings.warn("You have added a check_configuration method to your state change without specifying any configurable fields.")
        return {}

    @classmethod 
    def get_configurable_form_fields(cls):
        fields = {}
        for field_name, field_data in cls.get_configurable_fields().items():
            fields.update({ 
                field_name : {
                    "field_name": field_name,
                    "display": field_data["display"],
                    "type": field_data["type"] if "type" in field_data else "CharField",
                    "required": field_data["required"] if "required" in field_data else False,
                    "other_data": field_data["other_data"] if "other_data" in field_data else None,
                    "value": None
                }
            })
        return fields

    @classmethod
    def can_set_on_model(cls, model_name):
        """Tests whether a given model, passed in as a string, is in allowable target."""
        target_names = [model.__name__ for model in cls.get_settable_classes()]
        return True if model_name in target_names else False

    @classmethod
    def get_community_models(cls):
        """This helper method lets us indicate alternative community models as allowable targets for community actions."""
        from concord.actions.utils import get_all_community_models
        return get_all_community_models()

    def stringify_list(self, objlist):
        """Helper method for use in displaying change info.  Probably belongs elsewhere."""
        if len(objlist) > 1:
            objlist, last_item = objlist[:-1], objlist[-1]
        else:
            objlist, last_item = objlist, None
        display_string = ", ".join([str(item) for item in objlist])
        if last_item:
            display_string += " and " + str(last_item)
        return display_string

    def instantiate_fields(self):
        '''Helper method used by state change subclasses that have fields which require database
        lookups.  Not called by default, to prevent unnecessary db queries.'''
        return False

    def set_validation_error(self, message):
        """Helper method so all state changes don't have to import ValidationError"""
        self.validation_error = ValidationError(message)

    def validate(self, actor, target):
        ...

    def implement(self, actor, target, save=True):
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
        if "validation_error" in new_vars:
            del(new_vars)["validation_error"]
        return json.dumps(new_vars)

    @classmethod 
    def get_preposition(cls):
        """By default, we make changes "to" things but change types can override this default preposition with "for", "with", etc."""
        if hasattr(cls, "preposition"):
            return cls.preposition
        return "to"


class ChangeOwnerStateChange(BaseStateChange):
    description = "Change owner"
    preposition = "for"

    def __init__(self, new_owner_content_type, new_owner_id):
        self.new_owner_content_type = new_owner_content_type
        self.new_owner_id = new_owner_id

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "change owner of community to %s" % (self.new_owner)  

    def description_past_tense(self):
        return "changed owner of community to %s" % (self.new_owner) 

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target, save=True):

        # Given the content type and ID, instantiate owner
        ct = ContentType.objects.get_for_id(self.new_owner_content_type)
        model_class = ct.model_class()
        new_owner = model_class.objects.get(id=self.new_owner_id)

        target.owner = new_owner
        target.save()

        return target


class EnableFoundationalPermissionStateChange(BaseStateChange):
    description = "Enable the foundational permission"
    preposition = "for"
    is_foundational = True

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "enable the foundational permission" 

    def description_past_tense(self):
        return "enabled the foundational permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target, save=True):
        target.foundational_permission_enabled = True
        target.save()
        return target


class DisableFoundationalPermissionStateChange(BaseStateChange):
    description = "disable foundational permission"
    preposition = "for"
    is_foundational = True

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "disable the foundational permission" 

    def description_past_tense(self):
        return "disabled the foundational permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target, save=True):
        target.foundational_permission_enabled = False
        target.save()
        return target


class EnableGoverningPermissionStateChange(BaseStateChange):
    description = "Enable the governing permission"
    preposition = "for"
    is_foundational = True

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets() 

    def description_present_tense(self):
        return "enable the governing permission" 

    def description_past_tense(self):
        return "enabled the governing permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target, save=True):
        target.governing_permission_enabled = True
        target.save()
        return target


class DisableGoverningPermissionStateChange(BaseStateChange):
    description = "disable governing permission"
    preposition = "for"
    is_foundational = True

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "disable the governing permission" 

    def description_past_tense(self):
        return "disabled the governing permission"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target, save=True):
        target.governing_permission_enabled = False    
        target.save()    
        return target


class ViewStateChange(BaseStateChange):
    """'ViewStateChange' is a compromise name meant to indicate that,
    while the item inherits from BaseStateChange, it does not actually change
    any state - merely gets the specified fields."""
    description = "View"
    preposition = "for"

    def __init__(self, fields_to_include=None):
        self.fields_to_include = fields_to_include

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets() 

    @classmethod 
    def get_configurable_fields(self):
        return { "fields_to_include": { "display": "Fields that can be viewed" }}

    def description_present_tense(self):
        field_string = ", ".join(self.fields_to_include) if self.fields_to_include else "all fields"
        return "view %s" % field_string  

    def description_past_tense(self):
        field_string = ", ".join(self.fields_to_include) if self.fields_to_include else "all fields"
        return "viewed %s" % field_string  

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "fields_to_include" in configuration:
            if type(configuration["fields_to_include"]) != list:
                return False, "fields_to_include must be of type list, not %s " % str(type(configuration["fields_to_include"]))
            if not all(type(field) == str for field in configuration["fields_to_include"]):
                return False, "fields_to_include must be a list of strings"
        
        return True, ""

    def check_configuration(self, action, permission):
        '''All configurations must pass for the configuration check to pass.'''
        configuration = permission.get_configuration()
        missing_fields = []
        if "fields_to_include" in configuration:
            for targeted_field in self.fields_to_include:
                if targeted_field not in configuration["fields_to_include"]:
                    missing_fields.append(targeted_field)
        if missing_fields:
            return False, "Cannot view fields %s " % ", ".join(missing_fields)
        return True, None

    def validate(self, actor, target):
        """Checks if any specified fields are not on the target and, if there are any, returns False."""
        missing_fields = []
        if self.fields_to_include:
            for field in self.fields_to_include:
                if not hasattr(target, field):
                    missing_fields.append(field)
        if not missing_fields:
            return True
        self.set_validation_error("Attempting to view field(s) %s that are not on target %s" % (
            ", ".join(missing_fields), target))
        return False

    def implement(self, actor, target, save=True):
        """Gets data from specified fields, or from all fields, and returns as dictionary."""
        
        data_dict = {}

        target_data = target.get_serialized_field_data()

        if not self.fields_to_include:
            return target_data

        limited_data = {}
        for field in self.fields_to_include:
            limited_data.update({ field : target_data[field] })

        return limited_data


class ApplyTemplateStateChange(BaseStateChange):
    description = "Apply template"
    preposition = "to"
    pass_action = True

    def __init__(self, template_model_pk, supplied_fields=None):
        self.template_model_pk = template_model_pk
        self.supplied_fields = supplied_fields if supplied_fields else {}

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "apply template"  

    def description_past_tense(self):
        return "applied template"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target, action=None):
        # FIXME: I don't like that this is the only implement with a different signature :/
        # but I can't figure out a low-hack way to get the action this change is set on

        # Get the template model
        from concord.actions.models import TemplateModel
        template_model = TemplateModel.objects.get(pk=self.template_model_pk)

        container, log = template_model.template_data.apply_template(trigger_action=action, 
            supplied_fields=self.supplied_fields)

        return container
