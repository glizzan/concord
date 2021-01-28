from typing import TypeVar
from datetime import datetime

from django.contrib.auth.models import User

from concord.actions.models import PermissionedModel
from concord.actions.communities import Community









# The following types should cover any types handled by user:

ActorType = TypeVar('ActorType', User, int, str, list)
RoleType = TypeVar('RoleType', str)
DateTimeType = TypeVar('DateTimeType', datetime.datetime)
DurationType = TypeVar('DurationType', datetime.duration)
TextType = TypeVar('TextType', str)
IntegerType = TypeVar('IntegerType', int, str, float)
BooleanType = TypeVar('BooleanType', bool, str, int)
ResourceType = TypeVar('ResourceType', PermissionedModel)
CommunityType = TypeVar('CommunityType', Community)


# Handles conversion

class Converter(object):

    def convert(self, value, convert_to):
        return getattr(self, convert_to)(value)

    def to_pk_in_list(self, value):

        if isinstance(value, list):
            if len(value) == 1 and isinstance(value[0], int):
                return value

        if hasattr(value, "pk"):
            return [value.pk]

        try:
            value = int(value)
        except:
            return Exception(f"Cannot convert string {value} to integer")

        return [value]

    def to_user(self, value):

        if isinstance(value, User):
            return value

        if isinstance(value, list):
            if len(value) != 1:
                return Exception(f"Cannot convert value {value} of length {len(value)}, must be length 1")
            value = value[0]

        if isinstance(value, str):
            try:
                value = int(value)
            except:
                return Exception(f"Cannot convert string {value} to integer")

        if isinstance(value, int):
            try:
                return User.objects.get(pk=value)
            except:
                return Exception(f"Integer {value} is not a valid User pk, cannot convert value to actor")

        return Exception(f"value {value} cannot be converted to actor")

    def to_role_name(self):
        ...

    def to_resource(self):
        ...
