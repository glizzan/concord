import json, collections

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


################################
### ActorList Object & Field ###
################################


class ActorList(object):
    '''This custom object allows us to preferentially manipulate our actors as a list of
    PKs, so we don't have to constantly query the DB.  If pks and instances are not 
    identical, the pk_list is assumed authoritative.'''

    pk_list = []
    instance_list = []

    def __init__(self, actor_list=None):
        '''If an actor list is passed in, checks type of object in list. If the objects
        are user instances, saves them to instance_list and also generates a pk_list using
        their pk. If the objects are integers, saved to pk_list but do NOT generate
        instance list.'''

        if actor_list:
            first_item = actor_list[0]
            if type(first_item) == User:
                self.instance_list = actor_list
                self.as_pks()
            elif type(first_item) == int:
                self.pk_list = actor_list

    def as_pks(self):
        if not self.pk_list:  # pk_list is authoritative so we don't check len against instance_list
            self.pk_list = [actor.pk for actor in self.instance_list]
        return self.pk_list

    def as_instances(self):
        if not self.instance_list or len(self.instance_list != self.pk_list):
            self.instance_list = [User.objects.get(pk=pk) for pk in self.pk_list]
        return self.instance_list

    def is_empty(self):
        return not (self.pk_list or self.instance_list)

    def actor_in_list(self, actor):
        if type(actor) not in [User, int]:
            raise ValueError("Type of actor checked is ", type(actor), ", must be int or User")
        if type(actor) == User:
            actor = actor.pk
        return actor in self.pk_list

    def lists_are_equivalent(self):
        '''Helper method to check that pk_list and instance_list are equivalent.'''
        user_list = [instance.pk for instance in self.instance_list]
        return set(self.pk_list) == set(user_list)

    def add_actors(self, actors):
        """If actors are User instances, add to instance_list and pk_list; if pks, 
        add only to pk_list."""

        if not actors:
            print("Warning: empty list of actors passed to actorlist.add_actors.")
            return
        
        if type(actors[0]) == User:
            if any(not isinstance(actor, User) for actor in actors):
                raise ValueError("Non-User instance found in ActorList")
            self.instance_list = list(set(self.instance_list) | set(actors))
            self.pk_list = list(set(self.pk_list) | set([actor.pk for actor in actors]))
            return     
        
        if type(actors[0]) == int:
            if any(not isinstance(actor, int) for actor in actors):
                raise ValueError("Non-integer found in ActorList")
            self.pk_list = list(set(self.pk_list) | set(actors))
            return
        
        raise ValueError("Must add actors to actorlist as User or Int, not ", type(actors[0]))

    def remove_actors(self, actors, strict=True):
        """If actors are user instances, remove from instance_list and pk_list; if
        pks, remove only from pk_list.  If strict is true, all actors to be removed
        MUST be in the pk_list."""   

        if not actors:
            print("Warning: empty list of actors passed to actorlist.remove_actors.")
            return
    
        if type(actors[0]) == User:
            if any(not isinstance(actor, User) for actor in actors):
                raise ValueError("Non-User instance found in ActorList")
            instance_set = set(self.instance_list)
            pk_set = set(self.pk_list)
            for actor in actors:
                instance_set.discard(actor)
                # remove() throws KeyError if item does not exist
                pk_set.remove(actor.pk) if strict else pk_set.discard(actor.pk)
            self.instance_list = list(instance_set)
            self.pk_list = list(pk_set)
            return
             
        if type(actors[0]) == int:
            if any(not isinstance(actor, int) for actor in actors):
                raise ValueError("Non-integer found in ActorList")
            pk_set = set(self.pk_list)
            for actor_pk in actors:
                # remove() throws KeyError if item does not exist
                pk_set.remove(actor_pk) if strict else pk_set.discard(actor_pk)
            self.pk_list = list(pk_set)
            return

        raise ValueError("Must remove actors from actorlist as User or Int, not ", type(actors[0]))
        

def parse_actor_list_string(actor_list_string):
    try:
        pk_list = json.loads(actor_list_string)
    except json.decoder.JSONDecodeError as error:
        raise ValidationError("ActorListField was formatted wrongly and raised a JSONDecodeError")
    return ActorList(actor_list=pk_list)


class ActorListField(models.Field):
    """This custom field allows us to access a list of user objects or a list of user
    pks, depending on our needs."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'actorlist'  

    def from_db_value(self, value, expression, connection):
        if value is None:
            return ActorList()
        return parse_actor_list_string(value)

    def to_python(self, value):
        if isinstance(value, ActorList):
            return value
        if value is None:
            return ActorList()
        if type(value) == list and all([type(x) == int for x in value]):
            return ActorList(value)
        return parse_actor_list_string(value)

    def get_prep_value(self, value):
        if isinstance(value, ActorList):
            return json.dumps(value.as_pks())
        if value in [None, 'null', '[]']:
            return '[]'


###############################
### RoleList Object & Field ###
###############################


RolePair = collections.namedtuple('RolePair', 'community_pk role_name')

class RoleList(object):

    role_list = []

    def __init__(self, *, role_pair_list=None, list_of_pair_strings=None, community_pk=None, 
        role_name_list=None):
        '''Accepts a variety of formats, saves to role_list as a list of RolePair namedtuples.'''

        self.role_list = self.format_as_role_pair(role_pair_list=role_pair_list, 
            list_of_pair_strings=list_of_pair_strings, community_pk=community_pk, 
            role_name_list=role_name_list)

    def is_empty(self):
        return False if self.role_list else True
        
    def format_as_role_pair(self, *, role_pair_list=None, list_of_pair_strings=None, community_pk=None, 
        role_name_list=None):
        """Accepts a variety of formats and returns as list of role_pairs or an empty list."""

        role_list = []

        if role_pair_list and not (list_of_pair_strings or community_pk or role_name_list):
            if any(not isinstance(role_pair, RolePair) for role_pair in role_pair_list):
                raise ValueError("All items in role_pair_list must be of type RolePair, not ", type(role_pair))
            return role_pair_list

        if list_of_pair_strings and not (role_pair_list or community_pk or role_name_list):
            for pair_string in list_of_pair_strings:
                pk, name = pair_string.split("_")
                role_list.append(RolePair(community_pk=int(pk), role_name=name))
            return role_list

        if community_pk and role_name_list and not (list_of_pair_strings or role_pair_list):
            for role_name in role_name_list:
                role_list.append(RolePair(community_pk=int(community_pk), role_name=role_name))
            return role_list

        if not (role_pair_list or list_of_pair_strings or community_pk or role_name_list):
            return []

        raise ValueError("Invalid input to format_as_role_pair")

    def get_roles(self):
        return self.role_list

    def as_strings(self):
        role_strings = []
        for role in self.role_list:
            role_strings.append(str(role.community_pk) + "_" + role.role_name)
        return role_strings

    def role_name_in_list(self, role_name):
        for role in self.role_list:
            if role_name == role.role_name:
                return True
        return False

    def role_pair_in_list(self, role_pair):
        if type(role_pair) != RolePair:
            pk, name = role_pair.split("_")
            role_pair = RolePair(community_pk=int(pk), role_name=name)
        for existing_role in self.role_list:
            if existing_role.role_name == role_pair.role_name and \
                existing_role.community_pk == role_pair.community_pk:
                return True
        return False

    def add_roles(self, role_pair_list=None, list_of_pair_strings=None, community_pk=None, 
        role_name_list=None):

        roles = self.format_as_role_pair(role_pair_list=role_pair_list, 
            list_of_pair_strings=list_of_pair_strings, community_pk=community_pk, 
            role_name_list=role_name_list)

        role_set = set(self.role_list)
        for role in roles:
            role_set.add(role)
        self.role_list = list(role_set)

    def remove_roles(self, role_pair_list=None, list_of_pair_strings=None, community_pk=None, 
        role_name_list=None):

        roles = self.format_as_role_pair(role_pair_list=role_pair_list, 
            list_of_pair_strings=list_of_pair_strings, community_pk=community_pk, 
            role_name_list=role_name_list)

        role_set = set(self.role_list)
        for role in roles:
            role_set.discard(role)
        self.role_list = list(role_set)


def parse_role_list_string(role_list_string):
    try:
        list_of_pair_strings = json.loads(role_list_string)
    except json.decoder.JSONDecodeError as error:
        raise ValidationError("RoleListField was formatted wrongly and raised a JSONDecodeError")
    return RoleList(list_of_pair_strings=list_of_pair_strings)


class RoleListField(models.Field):
    """This custom field allows us to access our list of role pairs."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'rolelist'  

    def from_db_value(self, value, expression, connection):
        if value is None:
            return RoleList()
        return parse_role_list_string(value)

    def to_python(self, value):
        if isinstance(value, RoleList):
            return value
        if value is None:
            return RoleList()
        if type(value) == list and all([type(x) == RolePair for x in value]):
            return RoleList(value)
        return parse_role_list_string(value)

    def get_prep_value(self, value):
        if isinstance(value, RoleList):
            return json.dumps(value.as_strings())
        if value in [None, 'null', '[]']:
            return '[]'


###################################
### TemplateData Object & Field ###
###################################

"""
... could these just be unsaved versions of actual models?

sample use:  template.data.conditions.get_approval_conditions(target=community)

to update a permission to change the role, you'd do:
    template.data.permissions.change_role_on_permission(target_permission, new_role)

Okay, imagine you're on the front end, you see a template set with a community with role member_admins
that has permission to add_members, and you want to change it so that anyone with role member can add
members.  You'd hit an API change_role_on_template_permission with data - template ID, permission ID,
and new role.  That would call:
template(id=template_id).change_role_on_permission(permission_id=permission_id, new_role=new_role)

To edit someone else's template, you make a copy.  To edit your own template, you can edit as is.
So in the template object, you can create the span_ids, which can be passed back and forth to the
front end.

What is the POINT of having a customfield if everything is just dicts?  But I don't necessarily see
the point of creating instances here either.

"""

# class TemplateData(object):

#     community = None
#     permissions = []
#     conditions = []
#     owned_objects = []

#     def __init__(self, community, permissions=None, conditions=None, owned_objects=None):
