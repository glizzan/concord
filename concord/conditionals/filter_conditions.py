from abc import ABC, abstractmethod
from datetime import datetime, timezone
from contextlib import suppress

from concord.conditionals import utils, forms
from concord.utils.dependent_fields import crawl_objects
from concord.utils import field_utils
from concord.utils.converters import ConcordConverterMixin


class FilterCondition(ConcordConverterMixin, ABC):
    unique_name = None
    descriptive_name = None

    def __str__(self):
        return self.descriptive_name

    def condition_status(self, action):
        return self.check(action) if not self.inverse else not self.check(action)

    def description_for_passing_condition(self):
        print(f"WARNING: description for passing condition not specified for {self}")
        ...

    def __setattr__(self, attribute_name, attribute_value):
        with suppress(AttributeError):
            field = super().__getattribute__(attribute_name)
            if field and hasattr(field, "value"):
                field.value = attribute_value
                return
        super().__setattr__(attribute_name, attribute_value)

    def __getattribute__(self, attribute_name):
        """If the attribute is a Concord field, returns the value when referenced."""
        field = super().__getattribute__(attribute_name)
        if field and hasattr(field, "value"):
            return field.value
        return field

    @classmethod
    def get_configurable_fields(cls):
        """Returns field values as list instead of dict"""
        return [value for key, value in forms.form_dict_for_filter_condition(cls).items()]

    @property
    @classmethod
    def configurable_fields(cls):
        return cls.get_concord_fields_with_names.values()

    def get_configurable_fields_with_data(self, permission_data=None):
        """Returns form_dict with condition data set as value."""
        return forms.form_dict_for_filter_condition(self)

    def validate(self, permission, target):
        return True

    def get_matching_field(self, *, field_to_match, permission=None, target=None, action=None):

        # FIXME: target during validation and check are often the same but sometimes the target (aka thing being)
        # set on is not the same as the action target, so it can't really be validated :/

        crawl_tokens = field_to_match.split(".")

        if token[0] == "action" and action:
            return crawl_objects(crawl_tokens[1:], base=action)

        if token[0] == "action" and token[1] == "actor":
            ...

        if token[0] == "action" and token[1] == "target":
            return crawl_objects(crawl_tokens[2:], base=target)

        if token[0] == "action" and token[1] == "change":
            return crawl_objects(crawl_tokens[2:], base=permission)

        if token[0] == "target":
            return crawl_objects(crawl_tokens[1:], base=target)

        if token[0].lower() == target.__class__.__name__.lower():
            return crawl_objects(crawl_tokens[1:], base=target)


### REAL FILTERS ###


class ActorIsSameAs(FilterCondition):
    """
    Note: this replaces:
        'self only' (actor is the same as member_pk_list)
        'original creator only' (actor is the same as target.commented_on.creator)
        'commenter only' (actor is the same as target.creator)
    """
    unique_name = "actor_is_same_as"
    descriptive_name = "Actor is the same as"
    field_to_match = field_utils.CharField(label="Field to match", required=True)
    inverse = field_utils.BooleanField(label="Flip to inverse")

    def __init__(self, field_to_match, inverse=False):
        self.field_to_match = field_to_match
        self.inverse = inverse

    def validate(self, permission, target):

        field = self.get_matching_field(self.field_to_match, permission=permission, target=target)
        if not field:
            return False, f"No field found for '{field_to_match}'"

        convertible = field.can_convert_to("ActorField")

        if not field:
            return False, f"Field {field_to_match} cannot convert to Actor"

        return True

    def check(self, action):
        field = self.get_matching_field(self.field_to_match, action=action)
        if action.actor == field.to_ActorField:
            return True
        return False


class TargetType(FilterCondition):
    unique_name = "target_is_type"
    descriptive_name = "Target is of type"
    target_type = field_utils.PermissionedModelField(label="Limit targets to type", required=True)
    inverse = field_utils.BooleanField(label="Flip to inverse")

    def __init__(self, target_type, inverse=False):
        self.target_type = target_type
        self.inverse = inverse

    def check(self, action):
        if action.target.__class__.__name__ == self.target_type:
            return True
        return False


class FieldIs(FilterCondition):
    unique_name = "field_is"
    descriptive_name = "Field X is value Y"
    field_to_match = field_utils.CharField(label="Field to match", required=True)
    value_to_match = field_utils.CharField(label="Value to match", required=True)
    inverse = field_utils.BooleanField(label="Flip to inverse")

    def __init__(self, field_to_match, value_to_match, inverse):
        self.field_to_match = field_to_match
        self.value_to_match = value_to_match
        self.inverse = inverse

    def validate(self, permission, target):

        field = getattr(permission.change, self.field_to_match)
        if not field:
            return False, f"No field found for '{field_to_match}'"

        if not field.transform_to_valid_value(self.value_to_match):
            return False, f"{self.value_to_match} is not a valid value for {self.field_to_match}"

        return True, None

    def check(self, action):
        field = getattr(action.change, self.field_to_match)
        return field.value == self.value_to_match



### FIRST DRAFTS ####


class ActorUserCondition(FilterCondition):
    unique_name = "actor_user_age"
    descriptive_name = "Actor has been user longer than"
    duration = field_utils.DurationField(label="Length of time that must pass", required=True)
    inverse = field_utils.BooleanField(label="Flip to inverse (actor has been user less than...)")

    def __init__(self, duration=None, inverse=False):
        self.duration = duration
        self.inverse = inverse

    def description_for_passing_condition(self):
        units = utils.parse_duration_into_units(self.duration, measured_in="seconds")
        time_length = utils.display_duration_units(**units)
        return f"actor has been user longer than {time_length}"

    def check(self, action):
        if (datetime.now(timezone.utc) - action.actor.date_joined).seconds >= self.duration:
            return True
        return False


class ContainsText(FilterCondition):
    unique_name = "field_contains_text"
    descriptive_name = "Field contains text"
    field_to_match = field_utils.CharField(label="Field to match", required=True)
    inverse = field_utils.BooleanField(label="Flip to inverse")

    def __init__(self, field_to_match, text, inverse=False):
        self.field_to_match = field_to_match
        self.text = text
        self.inverse = inverse

    def validate(self, permission, target):

        field = self.get_matching_field(self.field_to_match, permission=permission, target=target)
        if not field:
            return False, f"No field {field_to_match} on target"

        convertible = field.can_convert_to("CharField")
        if not field:
            return False, f"Field {field_to_match} cannot convert to text"

        return True

    def check(self, action):
        field = self.get_matched_field([action, target])
        if self.text in field:
            return True
        return False


class ActorMemberCondition(FilterCondition):
    unique_name = "actor_user_age"
    descriptive_name = "Actor has been member of community longer than"
    duration = field_utils.DurationField(label="Duration of membership required", required=True)
    inverse = field_utils.BooleanField(label="Flip to inverse (actor has been member of community less than...)")

    def __init__(self, duration, inverse=False):
        self.duration = duration
        self.inverse = inverse

    def check(self, action):
        date_joined = Client(target=target.get_owner().Community.user_joined(action.actor))
        if datetime.datetime.now() - date_joined > self.duration:
            return True
        return False