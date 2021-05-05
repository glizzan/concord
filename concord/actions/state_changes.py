"""Defines state changes for concord.actions.models, as well as the BaseStateChange object from which all
state change objects inherit."""

from typing import List, Any

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.db import models, transaction

from concord.actions.models import TemplateModel
from concord.utils.lookups import get_all_permissioned_models, get_all_community_models
from concord.actions.utils import MockAction, AutoDescription
from concord.utils.converters import ConcordConverterMixin
from concord.utils import field_utils


class BaseStateChange(ConcordConverterMixin):
    """The BaseStateChange object is the object which all other state change objects inherit from. It has a
    variety of methods which must be implemented by those that inherit it."""

    instantiated_fields: List[str] = list()
    input_target: Any = None
    context_keys: List[str] = list()
    is_foundational = False
    section: str = "Miscellaneous"
    allowable_targets = ["all_models"]
    linked_filters = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        for field_name, field in self.get_concord_fields_with_names().items():
            value = kwargs.pop(field_name, None)
            if value is not None:
                setattr(self, field_name, value)
                continue
            if field.null_value:
                value = field.null_value
                value = {} if value == dict else value
                value = [] if value == list else value
            setattr(self, field_name, value)

    def serialize_fields(self):
        fields = {}
        for field_name, field in self.get_concord_fields_with_names().items():
            fields.update({field_name: getattr(self, field_name)})
        return fields

    @classmethod
    def get_change_type(cls):
        """Gets the full type of the change object in format 'concord.package.state_changes.SpecificStateChange'"""
        return cls.__module__ + "." + cls.__name__

    def is_conditionally_foundational(self, action):
        """Some state changes are only foundational in certain conditions. Those state changes override this
        method to apply logic and determine whether a specific instance is foundational or not."""
        return False

    @classmethod
    def can_set_on_model(cls, model_name):
        """Tests whether a given model, passed in as a string, is an allowable target."""
        target_names = [model.__name__ for model in cls.get_settable_classes()]
        return True if model_name in target_names else False

    @classmethod
    def get_models(cls, models):
        model_list = []
        for model in models:
            if model == "all_community_models":
                model_list += get_all_community_models()
            elif model == "all_models":
                model_list += get_all_permissioned_models()
            else:
                model_list.append(model)
        return model_list

    @classmethod
    def get_allowable_targets(cls):
        """Returns the classes that an action of this type may target."""
        return cls.get_models(cls.allowable_targets)

    @classmethod
    def get_settable_classes(cls):
        """Returns the classes that a permission with this change type may be set on. By default, this is the same as
        allowable_targets, but may be overridden by the settable_classes attribute, usually to add classes that an
        allowable target is nested on. Most likely called by the validate method in AddPermissionStateChange."""
        if hasattr(cls, "settable_classes"):
            return cls.get_models(cls.settable_classes)
        return cls.get_allowable_targets()

    def set_default_permissions(self, actor, instance):
        """Helper method to easily set default permissions on an object, called
        by implement when implement creates a new permissioned model."""
        from concord.permission_resources.utils import set_default_permissions
        return set_default_permissions(actor, instance)

    # Field methods

    # FIXME: delete now, I think?
    @classmethod
    def get_configurable_form_fields(cls):
        """Gets the configurable fields of a change object as form fields."""
        return {field_name: {**field.to_form_field(), **{"field_name": field_name}} for field_name, field
                in cls.get_concord_fields_with_names().items() if field_name in cls.configurable_fields}

    @classmethod
    def get_change_field_options(cls):
        """Gets a list of required parameters passed in to init, used by templates. Does not include optional
        parameters, as this may break the template referencing them if they're not there."""
        return [{"value": field_name, "text": field_name, "type": field.__class__.__name__}
                for field_name, field in cls.get_concord_fields_with_names().items() if field.required]

    # validation & implementation methods

    def set_validation_error(self, message):
        """Helper method so all state changes don't have to import ValidationError"""
        self.validation_error = ValidationError(message)

    def validate_against_model(self, target):

        if hasattr(self, "model_based_validation"):

            try:

                model_to_test = target if self.model_based_validation[0] == "target" else self.model_based_validation[0]
                field_dict = self.get_concord_field_instances()

                for field_name in self.model_based_validation[1]:

                    full_field = field_dict[field_name]
                    model_field = model_to_test._meta.get_field(field_name)
                    field_value = getattr(self, field_name)

                    if not field_value and not full_field.required:   # if no value but target field can be null
                        continue

                    model_field.clean(field_value, model_to_test)

                return True

            except ValidationError as error:
                if error.message in ['This field cannot be null.', 'This field cannot be blank.']:
                    message = f"Field '{field_name}' cannot be empty."
                else:
                    message = f"Error validating value {field_value} for field {field_name}: " + str(error)
                self.set_validation_error(message=message)
                return False

        return True

    def validate(self, actor, target):
        """Method to check whether the data provided to a change object in an action is valid for the
        change object. Optional exclude_fields tells us not to validate the given field."""

        if target._meta.model not in self.get_allowable_targets():
            self.set_validation_error(
                message=f"Object {str(target)} of type {target._meta.model} is not an allowable target")
            return False

        return self.validate_against_model(target)

    def implement(self, actor, target, **kwargs):
        """Method that carries out the change of state."""
        ...

    def implement_action(self, actor, target, action=None):
        """Wrapper for implement so we can refresh from database and make sure
        all actions touching this target happen sequentially and consistently."""
        with transaction.atomic():
            target = target._meta.model.objects.select_related().select_for_update().get(pk=target.pk)
            return self.implement(actor, target, action=action)

    # Text / description methods

    @classmethod
    def _description(cls):
        return AutoDescription(
            verb=cls.descriptive_text["verb"],
            default_string=cls.descriptive_text["default_string"],
            detail_string=cls.descriptive_text.get("detail_string", ""),
            preposition=cls.descriptive_text.get("preposition", "to"),
            past_tense=cls.descriptive_text.get("past_tense", None)
        )

    @classmethod
    def change_description(cls, capitalize=True):
        return cls._description().basic_description(capitalize)

    @classmethod
    def get_preposition(cls):
        return cls._description().preposition

    @classmethod
    def get_uninstantiated_description(cls):
        return cls._description().description_present_tense()

    def description_present_tense(self):
        """Returns the description of the state change object, in present tense."""
        return self._description().description_present_tense(change_obj=self)

    def description_past_tense(self):
        """Returns the description of the state change object, in past tense."""
        return self._description().description_past_tense(change_obj=self)

    # Context methods

    @classmethod
    def get_context_keys(cls):
        """Gets action as key by default, plus any context keys specified. If no context keys are specified and
        allowable_targets incldues only one model, grabs that model name as a valid context key."""

        defaults = ["action", settings.DEFAULT_COMMUNITY_MODEL]
        if not cls.context_keys and len(cls.get_allowable_targets()) == 1:
            return defaults + [cls.get_allowable_targets()[0].__name__.lower()]
        return defaults + cls.context_keys

    @classmethod
    def all_context_instances(cls, action):
        """Given the specific action that contains this change object, returns a dictionary
        with relevant model_instances. Used primarily by templates.

        We always return the action, the owning group by its model name, and the action target by its model name,
        with the state change able to specify additional objects."""

        context_dict = {
            "action": action,
            settings.DEFAULT_COMMUNITY_MODEL: action.target.get_owner(),
            action.target.__class__.__name__.lower(): action.target
        }

        context_dict = {**context_dict, **cls.get_context_instances(action)}
        return context_dict

    @classmethod
    def get_context_instances(cls, action):
        """Method to be optionally overridden by State Changes, adding context instances."""
        return {}


class ChangeOwnerStateChange(BaseStateChange):
    """State change for changing which community owns the object. Not to be confused with state changes which
    change who the owners are within a community."""

    descriptive_text = {
        "verb": "change",
        "default_string": "owner of community",
        "detail_string": "owner of community to {new_owner_id}",
        "preposition": "for"
    }

    is_foundational = True
    section = "Leadership"

    # Fields
    new_owner_content_type = field_utils.IntegerField(label="New owner's content type id", required=True)
    new_owner_id = field_utils.IntegerField(label="New owner's ID", required=True)

    def get_new_owner(self):
        """Helper method to get model instance of new owner from params."""
        content_type = ContentType.objects.get_for_id(self.new_owner_content_type)
        model_class = content_type.model_class()
        return model_class.objects.get(id=self.new_owner_id)

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target): return False

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

    def implement(self, actor, target, **kwargs):
        target.owner = self.get_new_owner()
        target.save()
        return target


class EnableFoundationalPermissionStateChange(BaseStateChange):
    """State change object for enabling the foundational permission of a permissioned model."""

    descriptive_text = {
        "verb": "enable",
        "default_string": "foundational permission",
        "preposition": "for"
    }

    section = "Permissions"
    is_foundational = True

    def implement(self, actor, target, **kwargs):
        target.foundational_permission_enabled = True
        target.save()
        return target


class DisableFoundationalPermissionStateChange(BaseStateChange):
    """State change object for disabling the foundational permission of a permissioned model."""

    descriptive_text = {
        "verb": "disable",
        "default_string": "foundational permission",
        "preposition": "for"
    }

    section = "Permissions"
    is_foundational = True

    def implement(self, actor, target, **kwargs):
        target.foundational_permission_enabled = False
        target.save()
        return target


class EnableGoverningPermissionStateChange(BaseStateChange):
    """State change object for enabling the governing permission of a permissioned model."""

    descriptive_text = {
        "verb": "enable",
        "default_string": "governing permission",
        "preposition": "for"
    }

    section = "Permissions"
    is_foundational = True

    def implement(self, actor, target, **kwargs):
        target.governing_permission_enabled = True
        target.save()
        return target


class DisableGoverningPermissionStateChange(BaseStateChange):
    """State change object for disabling the governing permission of a permissioned model."""

    descriptive_text = {
        "verb": "disable",
        "default_string": "governing permission",
        "preposition": "for"
    }

    section = "Permissions"
    is_foundational = True

    def implement(self, actor, target, **kwargs):
        target.governing_permission_enabled = False
        target.save()
        return target


class ViewStateChange(BaseStateChange):
    """ViewStateChange is a state change which doesn't actually change state. Instead, it returns the specified
    fields. It exists so we can wrap view permissions in the same model as all the other permissions."""

    descriptive_text = {
        "verb": "view",
        "default_string": "fields",
        "preposition": "for"
    }

    linked_filters = ["LimitedFieldsFilter"]

    # Fields
    fields_to_include = field_utils.ListField(label="Fields that can be viewed")

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

    def implement(self, actor, target, **kwargs):
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

    descriptive_text = {
        "verb": "apply",
        "past_tense": "applied",
        "default_string": "template",
        "preposition": "for"
    }

    pass_action = True
    linked_filters = ["CreatorFilter"]

    # Fields
    template_model_pk = field_utils.IntegerField(label="PK of Template to apply", required=True)
    supplied_fields = field_utils.DictField(label="Fields to supply when applying template", null_value=dict)
    template_is_foundational = field_utils.BooleanField(label="Template makes foundational changes")

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

    def implement(self, actor, target, **kwargs):
        """Implements the given template, relies on logic in apply_template."""
        action = kwargs.get("action", None)
        template_model = TemplateModel.objects.get(pk=self.template_model_pk)
        return template_model.template_data.apply_template(actor=actor, target=target, trigger_action=action,
                                                           supplied_fields=self.supplied_fields)
