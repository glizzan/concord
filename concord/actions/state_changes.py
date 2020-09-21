"""Defines state changes for concord.actions.models, as well as the BaseStateChange object from which all
state change objects inherit."""

from typing import List, Any
import json, warnings
from collections import namedtuple

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

from concord.actions.models import TemplateModel
from concord.actions.utils import get_all_permissioned_models, get_all_community_models, MockAction


InputField = namedtuple("InputField", ['name', 'type', 'required', 'validate'])


class BaseStateChange(object):
    """The BaseStateChange object is the object which all other state change objects inherit from. It has a
    variety of methods which must be implemented by those that inherit it."""

    instantiated_fields: List[str] = []
    input_fields: List[InputField] = []
    input_target: Any = None
    context_keys: List[str] = []
    is_foundational = False

    @classmethod
    def get_change_type(cls):
        """Gets the full type of the change object in format 'concord.package.state_changes.SpecificStateChange'"""
        return cls.__module__ + "." + cls.__name__

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

    def is_conditionally_foundational(self, action):
        """Some state changes are only foundational in certain conditions. Those state changes override this
        method to apply logic and determine whether a specific instance is foundational or not."""
        return False

    @classmethod
    def can_set_on_model(cls, model_name):
        """Tests whether a given model, passed in as a string, is in allowable target."""
        target_names = [model.__name__ for model in cls.get_settable_classes()]
        return True if model_name in target_names else False

    @classmethod
    def get_allowable_targets(cls):
        """Returns the classes that an action of this type may target."""
        return cls.get_all_possible_targets()

    @classmethod
    def get_settable_classes(cls):
        """Returns the classes that a permission with this change type may be set on.  This overlaps with
        allowable targets, but also includes classes that allowable targets may be nested on.  Most likely
        called by the validate method in AddPermissionStateChange."""
        return cls.get_allowable_targets()

    @classmethod
    def get_all_possible_targets(cls):
        """Helper method, gets all permissioned models in system that are not abstract."""
        return get_all_permissioned_models()

    @classmethod
    def get_community_models(cls):
        """Helper method which lets us use alternative community models as targets for community actions."""
        return get_all_community_models()

    # Field methods

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
    def get_change_field_options(cls):
        """Gets a list of required parameters passed in to init, used by templates. Does not include optional
        parameters, as this may break the template referencing them if they're not there."""
        return [{"value": field.name, "text": field.name, "type": field.type}
                for field in cls.input_fields if field.required]

    # validation & implementation methods

    def set_validation_error(self, message):
        """Helper method so all state changes don't have to import ValidationError"""
        self.validation_error = ValidationError(message)

    def validate(self, actor, target):
        """Method to check whether the data provided to a change object in an action is valid for the
        change object. Optional exclude_fields tells us not to validate the given field."""

        if target._meta.model not in self.get_allowable_targets():
            self.set_validation_error(
                message=f"Object {str(target)} of type {target._meta.model} is not an allowable target")
            return False

        try:
            target = self.input_target if self.input_target else target
            for field in self.input_fields:
                if field.validate:
                    field_value = getattr(self, field.name)
                    if not field_value and not field.required:
                        continue
                    target_field = target._meta.get_field(field.name)
                    target_field.clean(field_value, target)
            return True
        except ValidationError as error:
            message = f"Error validating value {field_value} for field {field.name}: " + str(error)
            self.set_validation_error(message=message)
            return False

    def implement(self, actor, target):
        """Method that carries out the change of state."""
        ...

    # Text / description methods

    @classmethod
    def get_preposition(cls):
        """By default, we make changes "to" things but change types can override this default preposition with
        "for", "with", etc."""
        if hasattr(cls, "preposition"):
            return cls.preposition
        return "to"

    @classmethod
    def get_configured_field_text(cls, configuration):
        """Gets additional text for permissions item instance descriptions from configured fields."""
        return ""

    def description_present_tense(self):
        """Returns the description of the state change object, in present tense."""
        return self.description

    def description_past_tense(self):
        """Returns the description of the state change object, in past tense."""
        ...

    # Context methods

    @classmethod
    def get_context_keys(cls):
        """Gets action as key by default, plus any context keys specified. If no context keys are specified and
        allowable_targets incldues only one model, grabs that model name as a valid context key."""

        defaults = ["action", settings.DEFAULT_COMMUNITY_MODEL]
        if not cls.context_keys and len(cls.get_allowable_targets()) == 1:
            return defaults + [cls.get_allowable_targets()[0].__name__.lower()]
        return defaults + cls.context_keys

    def all_context_instances(self, action):
        """Given the specific action that contains this change object, returns a dictionary
        with relevant model_instances. Used primarily by templates.

        We always return the action, the owning group by its model name, and the action target by its model name,
        with the state change able to specify additional objects."""

        context_dict = {
            "action": action,
            settings.DEFAULT_COMMUNITY_MODEL: action.target.get_owner(),
            action.target.__class__.__name__.lower(): action.target
        }

        context_dict = {**context_dict, **self.get_context_instances(action)}
        return context_dict

    def get_context_instances(self, action):
        """Method to be optionally overridden by State Changes, adding context instances."""
        return {}


class ChangeOwnerStateChange(BaseStateChange):
    """State change for changing which community owns the object. Not to be confused with state changes which
    change who the owners are within a community."""
    description = "Change owner"
    preposition = "for"
    is_foundational = True
    input_fields = [InputField(name="new_owner_content_type", type="ContentTypeField", required=True, validate=False),
                    InputField(name="new_owner_id", type="ObjectIDField", required=True, validate=False)]

    def __init__(self, new_owner_content_type, new_owner_id):
        self.new_owner_content_type = new_owner_content_type
        self.new_owner_id = new_owner_id

    def description_present_tense(self):
        return f"change owner of community to {self.new_owner_id}"

    def description_past_tense(self):
        return f"changed owner of community to {self.new_owner_id}"

    def get_new_owner(self):
        """Helper method to get model instance of new owner from params."""
        content_type = ContentType.objects.get_for_id(self.new_owner_content_type)
        model_class = content_type.model_class()
        return model_class.objects.get(id=self.new_owner_id)

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        try:
            new_owner = self.get_new_owner()
        except ObjectDoesNotExist:
            message = f"Couldn't find instance of content type {self.new_owner_content_type} & id {self.new_owner_id}"
            self.set_validation_error(message=message)
            return False
        if not hasattr(new_owner, "is_community") or not new_owner.is_community:
            message = f"New owner must be a descendant of community model, not {self.new_owner_content_type}"
            self.set_validation_error(message=message)
            return False
        return True

    def implement(self, actor, target):
        target.owner = self.get_new_owner()
        target.save()
        return target


class EnableFoundationalPermissionStateChange(BaseStateChange):
    """State change object for enabling the foundational permission of a permissioned model."""
    description = "Enable the foundational permission"
    preposition = "for"
    is_foundational = True

    def description_present_tense(self):
        return "enable the foundational permission"

    def description_past_tense(self):
        return "enabled the foundational permission"

    def implement(self, actor, target):
        target.foundational_permission_enabled = True
        target.save()
        return target


class DisableFoundationalPermissionStateChange(BaseStateChange):
    """State change object for disabling the foundational permission of a permissioned model."""
    description = "disable foundational permission"
    preposition = "for"
    is_foundational = True

    def description_present_tense(self):
        return "disable the foundational permission"

    def description_past_tense(self):
        return "disabled the foundational permission"

    def implement(self, actor, target):
        target.foundational_permission_enabled = False
        target.save()
        return target


class EnableGoverningPermissionStateChange(BaseStateChange):
    """State change object for enabling the governing permission of a permissioned model."""
    description = "Enable the governing permission"
    preposition = "for"
    is_foundational = True

    def description_present_tense(self):
        return "enable the governing permission"

    def description_past_tense(self):
        return "enabled the governing permission"

    def implement(self, actor, target):
        target.governing_permission_enabled = True
        target.save()
        return target


class DisableGoverningPermissionStateChange(BaseStateChange):
    """State change object for disabling the governing permission of a permissioned model."""
    description = "disable governing permission"
    preposition = "for"
    is_foundational = True

    def description_present_tense(self):
        return "disable the governing permission"

    def description_past_tense(self):
        return "disabled the governing permission"

    def implement(self, actor, target):
        target.governing_permission_enabled = False
        target.save()
        return target


class ViewStateChange(BaseStateChange):
    """ViewStateChange is a state change which doesn't actually change state. Instead, it returns the specified
    fields. It exists so we can wrap view permissions in the same model as all the other permissions."""
    description = "View"
    preposition = "for"
    input_fields = [InputField(name="fields_to_include", type="ListField", required=False, validate=False)]

    def __init__(self, fields_to_include=None):
        self.fields_to_include = fields_to_include

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
        if not super().validate(actor=actor, target=target):
            return False

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
    input_fields = [InputField(name="template_model_pk", type="ObjectIDField", required=True, validate=False),
                    InputField(name="supplied_fields", type="DictField", required=False, validate=False),
                    InputField(name="is_foundational", type="BooleanField", required=False, validate=False)]

    def __init__(self, template_model_pk, supplied_fields=None, is_foundational=False):
        self.template_model_pk = template_model_pk
        self.supplied_fields = supplied_fields if supplied_fields else {}
        self.is_foundational = is_foundational

    def description_present_tense(self):
        return "apply template"

    def description_past_tense(self):
        return "applied template"

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        # check template_model_pk is valid
        template = TemplateModel.objects.filter(pk=self.template_model_pk)
        if not template:
            self.set_validation_error(message=f"No template in database with ID {self.template_model_pk}")
            return False

        # check that supplied fields match template's siupplied fields
        needed_field_keys = set([key for key, value in template[0].get_supplied_fields().items()])
        supplied_field_keys = set([key for key, value in self.supplied_fields.items()])
        if needed_field_keys - supplied_field_keys:
            missing_fields = ', '.join(list(needed_field_keys - supplied_field_keys))
            self.set_validation_error(f"Template needs values for fields {missing_fields}")
            return False

        # attempt to apply actions (but rollback commit regardless)
        mock_action = MockAction(actor=actor, target=target, change=self)
        result = template[0].template_data.apply_template(
            actor=actor, target=target, trigger_action=mock_action, supplied_fields=self.supplied_fields,
            rollback=True)
        if "errors" in result:
            self.set_validation_error(f"Template errors: {'; '.join([error.message for error in result['errors']])}")
            return False

        return True

    def implement(self, actor, target, action=None):
        """Implements the given template, relies on logic in apply_template."""
        template_model = TemplateModel.objects.get(pk=self.template_model_pk)
        return template_model.template_data.apply_template(actor=actor, target=target, trigger_action=action,
                                                           supplied_fields=self.supplied_fields)
