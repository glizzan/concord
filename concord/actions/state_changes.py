"""Defines state changes for concord.actions.models, as well as the BaseStateChange object from which all
state change objects inherit."""

from typing import List
import json, warnings

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from concord.actions.models import TemplateModel
from concord.actions.utils import get_all_permissioned_models, get_all_community_models
from concord.actions.models import PermissionedModel


class BaseStateChange(object):
    """The BaseStateChange object is the object which all other state change objects inherit from. It has a
    variety of methods which must be implemented by those that inherit it."""

    allowable_targets: List[PermissionedModel] = []
    settable_classes: List[PermissionedModel] = []
    instantiated_fields: List[str] = []
    is_foundational = False

    @classmethod
    def get_change_type(cls):
        """Gets the full type of the change object in format 'concord.package.state_changes.SpecificStateChange'"""
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
        return get_all_permissioned_models()

    @classmethod
    def get_configurable_fields(cls):
        """Gets the fields of a change object which may be configured when used in a Permission model."""
        if hasattr(cls, 'check_configuration'):
            warnings.warn("You have added check_configuration method to state change without specifying "
                          + "any configurable fields.")
        return {}

    @classmethod
    def get_configurable_form_fields(cls):
        """Gets the configurable fields of a change object as form fields."""
        fields = {}
        for field_name, field_data in cls.get_configurable_fields().items():
            fields.update({
                field_name: {
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
        """Helper method which lets us use alternative community models as targets for community actions."""
        return get_all_community_models()

    @classmethod
    def get_preposition(cls):
        """By default, we make changes "to" things but change types can override this default preposition with
        "for", "with", etc."""
        if hasattr(cls, "preposition"):
            return cls.preposition
        return "to"

    def instantiate_fields(self):
        """Helper method used by state change subclasses that have fields which require database
        lookups.  Not called by default, to prevent unnecessary db queries."""
        return False

    def set_validation_error(self, message):
        """Helper method so all state changes don't have to import ValidationError"""
        self.validation_error = ValidationError(message)

    def validate(self, actor, target):
        """Method to check whether the data provided to a change object in an action is valid for the change object."""
        ...

    def implement(self, actor, target):
        """Method that carries out the change of state."""
        ...

    def get_change_data(self):
        """Given the python Change object, generates a json list of field names and values.  Does not include
        instantiated fields."""
        new_vars = vars(self)
        for field in self.instantiated_fields:
            if field in new_vars:
                del(new_vars)[field]
        if "validation_error" in new_vars:
            del(new_vars)["validation_error"]
        return json.dumps(new_vars)

    def description_present_tense(self):
        """Returns the description of the state change object, in present tense."""
        return self.description

    def description_past_tense(self):
        """Returns the description of the state change object, in past tense."""
        ...


class ChangeOwnerStateChange(BaseStateChange):
    """State change for changing which community owns the object. Not to be confused with state changes which
    change who the owners are within a community."""
    description = "Change owner"
    preposition = "for"

    def __init__(self, new_owner_content_type, new_owner_id):
        self.new_owner_content_type = new_owner_content_type
        self.new_owner_id = new_owner_id

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return f"change owner of community to {self.new_owner}"

    def description_past_tense(self):
        return "changed owner of community to {self.new_owner}"

    def validate(self, actor, target):
        """
        Put real logic here
        """
        return True

    def implement(self, actor, target):

        # Given the content type and ID, instantiate owner
        content_type = ContentType.objects.get_for_id(self.new_owner_content_type)
        model_class = content_type.model_class()
        new_owner = model_class.objects.get(id=self.new_owner_id)

        target.owner = new_owner
        target.save()

        return target


class EnableFoundationalPermissionStateChange(BaseStateChange):
    """State change object for enabling the foundational permission of a permissioned model."""
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

    def implement(self, actor, target):
        target.foundational_permission_enabled = True
        target.save()
        return target


class DisableFoundationalPermissionStateChange(BaseStateChange):
    """State change object for disabling the foundational permission of a permissioned model."""
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

    def implement(self, actor, target):
        target.foundational_permission_enabled = False
        target.save()
        return target


class EnableGoverningPermissionStateChange(BaseStateChange):
    """State change object for enabling the governing permission of a permissioned model."""
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

    def implement(self, actor, target):
        target.governing_permission_enabled = True
        target.save()
        return target


class DisableGoverningPermissionStateChange(BaseStateChange):
    """State change object for disabling the governing permission of a permissioned model."""
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

    def implement(self, actor, target):
        target.governing_permission_enabled = False
        target.save()
        return target


class ViewStateChange(BaseStateChange):
    """ViewStateChange is a state change which doesn't actually change state. Instead, it returns the specified
    fields. It exists so we can wrap view permissions in the same model as all the other permissions."""
    description = "View"
    preposition = "for"

    def __init__(self, fields_to_include=None):
        self.fields_to_include = fields_to_include

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    @classmethod
    def get_configurable_fields(cls):
        return {"fields_to_include": {"display": "Fields that can be viewed"}}

    def description_present_tense(self):
        return f"view {', '.join(self.fields_to_include) if self.fields_to_include else 'all fields'}"

    def description_past_tense(self):
        return f"viewed {', '.join(self.fields_to_include) if self.fields_to_include else 'all fields'}"

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        if "fields_to_include" in configuration:
            if not isinstance(configuration["fields_to_include"], list):
                field_type = str(type(configuration['fields_to_include']))
                return False, f"fields_to_include must be type list, not {field_type}"
            if not all(isinstance(field, str) for field in configuration["fields_to_include"]):
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
            return False, f"Cannot view fields {', '.join(missing_fields)}"
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
        self.set_validation_error(f"Attempting to view field(s) {', '.join(missing_fields)} not on target {target}")
        return False

    def implement(self, actor, target):
        """Gets data from specified fields, or from all fields, and returns as dictionary."""

        target_data = target.get_serialized_field_data()

        if not self.fields_to_include:
            return target_data

        limited_data = {}
        for field in self.fields_to_include:
            limited_data.update({field: target_data[field]})

        return limited_data


class ApplyTemplateStateChange(BaseStateChange):
    """State change object for applying a template."""
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

        template_model = TemplateModel.objects.get(pk=self.template_model_pk)

        container, log = template_model.template_data.apply_template(trigger_action=action,
                                                                     supplied_fields=self.supplied_fields)

        return container
