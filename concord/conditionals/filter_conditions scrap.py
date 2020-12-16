# from abc import ABC, abstractmethod

# from concord.actions.concord_types import (ActorType, RoleType, DateTimeType, DurationType, TextType, IntegerType,
#                                            BooleanType, ResourceType, CommunityType)


# class FilterCondition(ABC):
#     unique_name = None
#     readable_name = None

#     def validate(self, permission, target):
#         return True

#     def check(self, action, target):
#         ...

#     def get_field_and_annotation(self, field_to_match, permission_or_action, target):
#         """Gets a given field and its annotation."""
#         # get field using logic in replace_fields
#         return ("field_name", "annotation")

#     def validate_match_field(self, field_to_match, permission, target):
#         """Validates that the field_to_match exists on the object. Also checks type annotations."""

#         # does it exist?
#         field = self.get_field(field_to_match, permission, target)
#         if not field:
#             return False

#         # do annotations match?
#         field_annotation = self.__init__.__annotations__.get("field_to_match", None)
#         obj_field_annotation = # getting the annotation will only work here






#     def match_field(self, field_to_match, obj):
#         """.member_pk_list"; likely involves going down the
#           . path one step at a time like in replacer()
#         TODO: catch error (or cause compile-time error?) if field_to_match (or 'field_to_match') isn't annotated?

#         """
#         obj_field_annotation = obj.__init__.__annotations__[field_to_match]
#         if field_annotation != obj_field_annotation:
#             print(f"{field_annotation} does not match {obj_field_annotation}")
#             return False
#         return True


# class ActorUserCondition(FilterCondition):
#     unique_name = "actor_user_age"
#     readable_name = "Actor has been user longer than"

#     def __init__(self, duration):
#         self.duration = duration

#     def validate(self, permission, target):
#         ... # duration related validation

#     def check(self, action, target):
#         if datetime.datetime.now() - action.actor.date_created > self.duration:
#             return True
#         return False


# class ContainsText(FilterCondition):
#     unique_name = "field_contains_text"
#     readable_name = "Field contains text"

#     def __init__(self, field_to_match: TextType, text):
#         self.field_to_match = field_to_match
#         self.text = text

#     def validate(self, permission, target):
#         # do any text validation
#         return self.validate_match_field(self.field_to_match, permission, target)

#     def check(self, action, target):
#         field = getattr(action.change, self.field_to_match)
#         if self.text in field:
#             return True
#         return False


# class ActorIsSameAs(FilterCondition):
#     unique_name = "actor_is_same_as"
#     readable_name = "Actor is the same as"

#     def __init__(self, field_to_match: ActorType):
#         self.field_to_match = field_to_match

#     def validate(self, permission, target):
#         return self.match_field(self.field_to_match, permission, target)

#     def check(self, action, target):
#         field = self.get_field(self.field_to_match, action, target)
#         user = converter.convert(field, "to_user")
#         if action.actor == user:
#             return True
#         return False







#     # FIXME: this allows for us to say "actor is the target creator" but not, say, actor is creator of
#     # thing with relationship to target --- need to make it recursive somehow, like if you can follow along,
#     # target then commented on then creator, etc

#     # maybe a special type/class called a ref?

#     """
#     In interface, maybe dependent field just gives you a bunch of options like:
#     action, actor, target, member_pk_list etc - basically all of the options at every level, filtered by
#     type (actortype, texttype, etc).  And when you select it, it knows the string version
#     (action vs action.change.member_pk_list)
#     """

#     """
#     When you're selecting a field option, it will be something like "action.change.member_pk_list" which
#     can then be interpreted here, possibly duplicating some of the replacer logic.

#     """


# class ActorActivity(FilterCondition):
#     unique_name = "actor_activity"
#     readable_name = "actor has {verb} {count}"


# """
# filter_model = get_filter_model()
# passes_filter = filter_model(configured_value).check(action)

# "Actor is the same as the creator of the target"
# ActorIs = get_filter_model()
# passes_filter = ActorIs("target creator).check(action)

# "Actor is the person being removed from the group"
# ActorIs = get_filter_model()
# passes_filter = ActorIs("member_pk_list").check(action)


# NOTE: this is the same pattern as condition's dependent field - trying to figure out what the user can set
# by looking up what's possible on the state change



# More generally, this FilterCondition (see ActorActivity) speaks to my focus on objects.  Like, if I want to
# let people choose based on activity, do I have to hard code all of it, every possibly type of variation
# people could use?  There's GOT to be a better way.


#     def check(action, ):

#         if action.actor has_conditions


# """

# """

# The issue in all of these places (templates, dependent fields in decision conditions, dependent fields
# in filter conditions) is wanting to allow for flexibility but still being able to constrain.

# We want to be able to limit "actor is same as" to a thing that can be translated into a user object. We want to
# reject (or never provide as options) things that can't be translated into a user object, and we want to
# seamlessly translate things that can be into their correct objects.

# We can create a single function that translates an input into a user object, or into any other type. It just
# has to try things in an order and eventually fail if none work.


# DateTimeField - vs DurationField?
# Text
# Boolean
# Integer
# Actor
# Role
# Resource
# Community





# """

# """

# STEPS:

# (1) - change replacer fields to not do transforms; instead, transforms are in the setter field of an object
# NO NO NO - that only works for custom model fields, it won't work for, say, setting a primary key field for
# instance.


# (2) - refactor replace_fields to be used by filter_conditions as well as decision_conditions and templates


# EAYRAYGHHGA














# """