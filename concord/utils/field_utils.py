import json
from contextlib import suppress


# TODO: fields shouldn't be storing values, need to remove once no longer depended on

class BaseConcordField(object):
    converts_to = list()
    label = None
    required = False
    default = None
    value = None
    field_name = None
    full_name = None
    null_value = None

    def __init__(self, label, required=None, default=None, value=None, full_name=None, null_value=None, **kwargs):
        self.label = label
        self.required = required if required else self.required
        self.default = default if default else self.default
        self.value = value if value else self.value
        self.full_name = full_name if full_name else self.full_name
        self.null_value = null_value if null_value else self.null_value

    def to_form_field(self):
        return {"label": self.label, "required": self.required, "default": self.default, "value": self.value,
                "full_name": self.full_name, "type": self.__class__.__name__}

    def to_BooleanField(self):
        return bool(self.value)

    def can_convert_to(self, field_type):
        return field_type in self.converts_to


class RoleListField(BaseConcordField):
    converts_to = ['RoleField', 'CharField', 'BooleanField']

    def validate(self, value):
        value = value if value else self.value
        if not value:
            raise ValueError(f"Value not provided for validation of {self}")
        if type(value) != list:
            raise ValueError(f"Role list field must be list, not {type(value)}")
        if not all([type(item) == str for item in value]):
            raise ValueError("Role list must contain all strings.")
        return True

    def transform_to_valid_value(self, value):

        if type(value) == str:
            try:
                value = json.loads(value)
            except ValueError:
                ...

        if type(value) != list:
            try:
                value = list(value)
            except TypeError:
                ...

        with suppress(ValueError):
            is_valid = self.validate(value)
            if is_valid:
                return value

    def to_RoleField(self):
        if len(self.value) == 0:
            return ""
        return self.value[0]

    def to_CharField(self):
        return ", ".join(self.value)


class RoleField(BaseConcordField):
    converts_to = ['RoleListField', 'CharField', 'BooleanField']

    def to_RoleListField(self):
        return [self.value]

    def to_CharField(self):
        return self.value


class ActorListField(BaseConcordField):
    # Note: Actor *Concord* fields (as opposed to on Django models) are stored as pk
    converts_to = ['ActorField', 'CharField', 'IntegerField', 'BooleanField']

    def validate(self, value):
        value = value if value else self.value
        if not value:
            raise ValueError(f"Value not provided for validation of {self}")
        if type(value) != list:
            raise ValueError(f"Actor list field must be list, not {type(value)}")
        if not all([type(item) == int for item in value]):
            raise ValueError("Role list must contain all integers.")
        return True

    def to_ActorField(self):
        if len(self.value) == 0:
            return None
        return self.value[0]

    def transform_to_valid_value(self, value):

        if type(value) == str:
            try:
                value = json.loads(value)
            except ValueError:
                ...

        if type(value) != list:
            try:
                value = list(value)
            except TypeError:
                ...

        try:
            value = [int(val) for val in value]
        except ValueError:
            ...

        with suppress(ValueError):
            is_valid = self.validate(value)
            if is_valid:
                return value


class ActorField(BaseConcordField):
    # Note: Actor *Concord* fields (as opposed to on Django models) are stored as pk
    converts_to = ['ActorListField', 'CharField', 'IntegerField', 'BooleanField']


class PermissionedModelField(BaseConcordField):

    def __init__(self, *args, **kwargs):   # Allows us to restrict to only certain types of permissioned models
        self.restrict_to = kwargs.pop("restrict_to", list())
        super().__init__(*args, **kwargs)


class DictField(BaseConcordField):
    ...


class ListField(BaseConcordField):
    ...


class IntegerField(BaseConcordField):
    ...


class BooleanField(BaseConcordField):
    ...


class CharField(BaseConcordField):
    ...


class DateTimeField(BaseConcordField):
    ...


class DurationField(BaseConcordField):
    ...


def get_field(field_name):
    # FIXME: this is a hack
    if field_name == "RoleListField": return RoleListField
    if field_name == "RoleField": return RoleField
    if field_name == "ActorListField": return ActorListField
    if field_name == "ActorField": return ActorField
    if field_name == "PermissionedModelField": return PermissionedModelField
    if field_name == "DictField": return DictField
    if field_name == "ListField": return ListField
    if field_name == "IntegerField": return IntegerField
    if field_name == "BooleanField": return BooleanField
    if field_name == "CharField": return CharField
    if field_name == "DateTimeField": return DateTimeField
    if field_name == "DurationField": return DurationField


def get_convert_map():

    convert_map = {}

    for field in [RoleListField, RoleField, ActorListField, ActorField]:
        for convert_field in field.converts_to:
            convert_map[convert_field] = convert_map.get(convert_field, []) + [field.__class__.__name__]

    return convert_map
