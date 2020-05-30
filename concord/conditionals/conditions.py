"""

Problem I'm trying to solve here:

I need to be able to treat permissions, conditions, and actions as things that can be instantiated in the database 
but also as hypotheticals that can be exposed to the user, configured, stored, and then eventually instantiated
multiple times.

We *already* do this with conditions & condition templates, but not necessarily well.  And then there are much
less extensive hacks for permissions (stored as permission_data in condition templates) and MockActions for
ActionContainer.

The question, really, is *what do I need form the hypothetical version*?  Once I understand that, I can create
an approach to dual/multiple interfaces.


- Another confusing elemenet is that permission is nested *with* condition data in condition template - the 
template is not purely/necessarily a map onto just condition but onto both condition and permission



The thing that's confusing is the DB calls, I think.  If there's an interface that *doesn't make DB call*
unless explicitly told to, then it could otherwise be treated equally.

Anything else different?

- well yes though - a hypothetical condition won't have an action associated with it
- BUT you could easily patch it to, you could create a non DB condition and say hey, permission, this is the 
condition to link to
- so it's actually the relationships - which are themselves DB calls by default - that are the issue
- which makes sense given the struggle I had with templates!
- and in the templates, I solved it by creating a dict which generated a unique ID and used it as a map

- could we use descriptors to override how these relationships are made?  so 
condition.action = action means 





"""


















"""
Maybe delete everything below this line????



This module defines two Abstract Base Classes with corresponding interfaces for working with conditions:

- ConditionObject: an interface for condition_templates, also known as conditionals, which are set on permissions or
 on leadership roles and which contain information for creating actual condition instances associated with specific actions

- ConditionTemplateObject: an interface for conditions, which are created when a specific action triggers them

Originally, we just had Condition and ConditionTemplate models in Django, but these objects don't always relate to
the database in the same way.  For example, Conditions that are instantiated models in Django store their data as
rows in various tables, while Conditions that are stored as configurations in a Condition Template model are 
stored in a cell in one specific table.

# TODO: determine if we need ABCs for individual conditions like vote_condition as well, in which case it'd be
those things added as mixins to their corresponding model.
"""
from abc import ABC


class ConditionObject(ABC):

    action =  models.IntegerField()
    condition_template =  models.IntegerField()
    descriptive_name = "condition"
    has_timeout = False

    def get_name(self):
        return f"{self.descriptive_name} with pk {self.get_pk()}"

    def get_pk(self):
        if hasattr(self, pk):
            return pk
        return None

    def get_action(self):
        ac = ActionClient(system=True)
        return ac.get_action_given_pk(pk=self.action)

    def user_condition_status(self, user):
        """User condition status is a shortcut which helps us determine if a user can take an action on a condition
        without actually creating an action. This is useful in determining what to show the user on the front-end.
        We assume that by the time user_condition_status is called the user has passed the permissions system, and so
        this status is to check instance-specific issues, like preventing a person who has already voted from voting
        again."""
        # FIXME: this seems like something that could be done better with provisional actions if that gets developed
        return True, ""

    # Class methods with default implementation

    @classmethod
    def get_slug(cls):
        return cls.__name__.lower()

    @classmethod
    def get_configurable_fields(cls):
        """Returns field values as list instead of dict"""
        return [ value for key, value in cls.configurable_fields().items() ]

    @classmethod
    def get_configurable_field_names(cls):
        """Return field names as list."""
        return [ key for key, value in cls.configurable_fields().items() ]

    @classmethod
    def get_form_dict_for_field(cls, field):
        return { 
            'name': field.name, 
            'type': field.__class__.__name__, 
            'required': "required" if field.blank else "", 
            'value': field.default 
        }

    @classmethod
    def permission_field_map(cls, field_name):
        '''All conditions have at least one permission type that's used to update the permission (for instance,
        'approve' for ApprovalCondition, 'vote' for VoteCondition, etc).  The permission field map maps a short
        field_name like 'approve_roles' to the role field on the verbose concord.conditionals.statechange.ApprovalStatechange,
        which is defined in a condition model's permission_map attribute.'''
        return cls.permission_map[field_name], field_name.split("_")[1]

    # Methods models must implement themselves

    @classmethod
    @abstractmethod
    def configurable_fields(cls):
        '''All conditions must supply their own version of the configurable_fields method, 
        which should return a dict with field names as keys and field objects as values.'''
        return {}

    @abstractmethod
    def description_for_passing_condition(self, fill_dict):
        """This method returns a verbose, human-readable description of what will fulfill this condition.  It optionally
        accepts permission data from the configured condition_template to be more precise about who can do what."""
        pass

    @abstractmethod
    def display_fields(self):
        """This method returns a list of fields and their values which can be shown to the user. Some overlap with
        get_configurable_fields_with_data since in many cases we're just showing the configured fields, but some
        data may be specific to the condition instance.  Note that we do not, for now, return permission data."""
        pass

    @abstractmethod
    def condition_status(self):
        """This method returns one of status 'approved', 'rejected', or 'waiting', after checking the condition
        for its unqiue status logic."""
        pass

    @abstractmethod
    def display_status(self):
        """This method returns a more verbose, human-readable description of the condition status, after checking
        the condition for its unique status logic."""
        pass