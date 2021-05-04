from contextlib import suppress
import json

from concord.utils import field_utils


class Filter(object):

    linked = False

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def condition_status(self, action):
        result, message = self.check(action=action)
        if not result:
            action.add_log({"rejection_reason": message, "approved_through": None})
        return "approved" if result else "rejected"

    @classmethod
    def get_input_field_objects(cls):
        return {key: value for key, value in cls.__dict__.items() if hasattr(value, "label")}

    def get_input_field_values(self):
        field_values = {}
        for field_name, field in self.get_input_field_objects().items():
            current_value = getattr(self, field_name)
            if hasattr(current_value, "label"):
                current_value = None  # if the value on the instance is a ConcordField, that means it's not set
            field_values.update({field_name: current_value})
        return field_values

    def validate(self, change_object):
        # should automatically validate values against input field types
        return True, None

    # text logic

    @property
    def configured_description(self):
        return self.configured_description_text

    def get_descriptive_name(self):
        return self.descriptive_name

    def get_configured_name(self):
        if hasattr(self, "configured_name"):
            return self.configured_name.format(**self.get_input_field_values())
        return self.get_descriptive_name()

    # form logic

    @classmethod
    def get_fields_as_form(cls):
        form = {}
        for field_name, field in cls.get_input_field_objects().items():
            form_dict = field.to_form_field()
            form_dict.update({"field_name": field_name, "can_depend": False, "display": field.label})
            form.update({field_name: form_dict})
        return form

    def get_form_fields_with_data(self):
        existing_data = self.get_input_field_values()
        form_dict = {}
        for field_name, form in self.get_fields_as_form().items():
            if existing_data[field_name]:
                form["value"] = existing_data[field_name]
            form_dict.update({field_name: form})
        return form_dict

    @classmethod
    def get_configurable_fields(cls):
        return cls.get_fields_as_form()  # included to fit with existing old naming system  #FIXME: refactor


class SelfMembershipFilter(Filter):
    descriptive_name = "the actor is the member"
    linked = True

    def check(self, *, action, **kwargs):
        """Action field should always be a list of user pks. We look to see if the action's actor is the
        only pk in that field."""
        return [action.actor.pk] == action.change.member_pk_list, "actor is not member"


class FieldMatchesFilter(Filter):
    descriptive_name = "a field matches a value"
    configured_name = "{field_to_match} matches '{value_to_match}'"

    field_to_match = field_utils.CharField(label="Field to match", required=True)
    value_to_match = field_utils.CharField(label="Value to match", required=True)

    # TODO: for now we can only match change object fields, probably should be more flexible - use crawl objects?

    def validate(self, permission):
        change_obj = permission.get_state_change_object()
        if not hasattr(change_obj, self.field_to_match):
            return False, f"No field '{self.field_to_match}' on this permission"
        return True, None

    def check(self, *, action, **kwargs):
        """The contents of the action field should equal the custom text."""
        field_value = getattr(action.change, self.field_to_match)
        return field_value == self.value_to_match, "field does not match"


class FieldContainsFilter(Filter):
    descriptive_name = "a field contains specific text"
    configured_name = "{field_to_match} {verb} '{value_to_match}'"

    field_to_match = field_utils.CharField(label="Field to look in", required=True)
    value_to_match = field_utils.CharField(label="Text to search for", required=True)
    inverse = field_utils.BooleanField(label="Reverse (only allowed if it does NOT contain above text)", default=False)

    # TODO: for now we can only match change object fields, probably should be more flexible - use crawl objects?
    # TODO: should either restrict this to text fields or find a coherent way of translating non-text fields to text

    def does_not_contain(self):
        if isinstance(self.inverse, bool):
            return self.inverse
        return False

    def validate(self, permission):
        change_obj = permission.get_state_change_object()
        if not hasattr(change_obj, self.field_to_match):
            return False, f"No field '{self.field_to_match}' on this permission"
        return True, None

    def check(self, *, action, **kwargs):
        """The contents of the action field should equal the custom text."""
        field_value = getattr(action.change, self.field_to_match)
        if self.does_not_contain:
            failure_msg = f"field '{self.field_to_match}' contains '{self.value_to_match.lower()}'"
            return self.value_to_match.lower() not in field_value.lower(), failure_msg
        failure_msg = f"field '{self.field_to_match}' does not contain '{self.value_to_match.lower()}'"
        return self.value_to_match.lower() in field_value.lower(), failure_msg

    def get_configured_name(self):
        if hasattr(self, "configured_name"):
            text_dict = self.get_input_field_values()
            text_dict["verb"] = "does not contain" if self.does_not_contain() else "contains"
            return self.configured_name.format(**text_dict)
        return self.get_descriptive_name()


class RoleMatchesFilter(Filter):
    descriptive_name = "the role's name is a specific value"
    configured_name = "the role's name is '{role_name}'"
    linked = True

    role_name = field_utils.RoleField(label="Role to match", required=True)

    def check(self, *, action, **kwargs):
        return action.change.role_name == self.role_name, f"the role name does not match {self.role_name}"


class TargetTypeFilter(Filter):
    descriptive_name = "the target of the action is a specific type"
    configured_name = "the target of the action is {target_type}"

    target_type = field_utils.PermissionedModelField(label="Limit targets to type", required=True)

    def check(self, *, action, **kwargs):
        failure_msg = f"target is not {self.target_type}"
        return action.target.__class__.__name__.lower() == self.target_type.lower(), failure_msg


class CreatorOfCommentedFilter(Filter):
    linked = True
    descriptive_name = "the actor created the thing being commented on"

    def check(self, action, **kwargs):
        failure_msg = "the actor did not create the thing being commented on"
        with suppress(AttributeError):
            return action.actor == action.target.commented_object.creator, failure_msg  # action target is a comment
        with suppress(AttributeError):
            return action.actor == action.target.creator, failure_msg  # action target is the thing itself
        with suppress(AttributeError):
            return action.actor == action.target.commented_object.author, failure_msg  # creator is called author
        with suppress(AttributeError):
            return action.actor == action.target.author, failure_msg
        return False, failure_msg


class CreatorFilter(Filter):
    descriptive_name = "the actor is the creator"

    def check(self, action, **kwargs):
        failure_msg = "the actor is not the creator"
        with suppress(AttributeError):
            if action.target.creator:
                return action.actor == action.target.creator, failure_msg
        with suppress(AttributeError):
            if action.target.author:
                return action.actor == action.target.author, failure_msg  # sometimes creator is called author
        return False, failure_msg


class CommenterFilter(Filter):
    linked = True
    descriptive_name = "the actor wrote the comment"

    def check(self, *, action, **kwargs):
        return action.actor == action.target.commenter, "the actor didn't write the comment"


class LimitedFieldsFilter(Filter):
    linked = True
    descriptive_name = "fields are limited"
    configured_name = "fields are limited to {limited_fields}"

    limited_fields = field_utils.ListField(label="Limit fields to", required=True)

    def check(self, *, action, **kwargs):
        failure_msg = f"fields were limited to {self.limited_fields}"
        if not action.change.fields_to_include:
            # We're limited our fields, but if 'fields_to_include' is not set that means "get everything"
            return False, failure_msg
        limited_fields = json.loads(self.limited_fields)
        for field in action.change.fields_to_include:
            if field not in limited_fields:
                return False, failure_msg
        return True, failure_msg
