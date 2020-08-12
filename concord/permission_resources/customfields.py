"""Custom Fields used by Permission Resource models."""

import json, logging

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


logger = logging.getLogger(__name__)


################################
### ActorList Object & Field ###
################################


class ActorList(object):
    """This custom object allows us to preferentially manipulate our actors as a list of
    PKs, so we don't have to constantly query the DB.  If pks and instances are not
    identical, the pk_list is assumed authoritative."""

    pk_list = []
    instance_list = []

    def __init__(self, actor_list=None):
        """If an actor list is passed in, checks type of object in list. If the objects
        are user instances, saves them to instance_list and also generates a pk_list using
        their pk. If the objects are integers, saved to pk_list but do NOT generate
        instance list."""

        if actor_list:
            first_item = actor_list[0]
            if isinstance(first_item, User):
                self.instance_list = actor_list
                self.as_pks()
            elif isinstance(first_item, int):
                self.pk_list = actor_list
            else:
                raise ValidationError(message="actor_list must be User objects or pks, not " + str(type(first_item)))

    def as_pks(self):
        """Get actors as pk."""
        if not self.pk_list:  # pk_list is authoritative so we don't check len against instance_list
            self.pk_list = [actor.pk for actor in self.instance_list]
        return self.pk_list

    def as_instances(self):
        """Get actors as instances, checking first to make sure the list of instances is the same length as pks."""
        if not self.instance_list or len(self.instance_list) != len(self.pk_list):
            self.instance_list = [User.objects.get(pk=pk) for pk in self.pk_list]
        return self.instance_list

    def is_empty(self):
        """Returns true if there's no actors in lists."""
        return not (self.pk_list or self.instance_list)

    def actor_in_list(self, actor):
        """Checks if a given actor is in the actor list."""
        if type(actor) not in [User, int]:
            raise ValueError("Type of actor checked is ", type(actor), ", must be int or User")
        if isinstance(actor, User):
            actor = actor.pk
        return actor in self.pk_list

    def lists_are_equivalent(self):
        """Helper method to check that pk_list and instance_list are equivalent."""
        user_list = [instance.pk for instance in self.instance_list]
        return set(self.pk_list) == set(user_list)

    def add_actors(self, actors):
        """If actors are User instances, add to instance_list and pk_list; if pks,
        add only to pk_list."""

        if not actors:
            logging.warning(f"falsy value for actors passed to actorlist.add_actors (value: {actors}, " +
                            f"type: {type(actors)}).")
            return

        if not isinstance(actors, list):
            raise ValueError(f"Must pass actors as list, not {type(actors)} (value: {actors})")

        if isinstance(actors[0], User):
            if any(not isinstance(actor, User) for actor in actors):
                raise ValueError("Non-User instance found in ActorList")
            self.instance_list = list(set(self.instance_list) | set(actors))
            self.pk_list = list(set(self.pk_list) | set([actor.pk for actor in actors]))
            return

        if isinstance(actors[0], int):
            if any(not isinstance(actor, int) for actor in actors):
                raise ValueError("Non-integer found in ActorList")
            self.pk_list = list(set(self.pk_list) | set(actors))
            return

        raise ValueError(f"Must add actors to actorlist as User or Int, not {type(actors[0])} (actors: {actors})")

    def remove_actors(self, actors, strict=True):
        """If actors are user instances, remove from instance_list and pk_list; if
        pks, remove only from pk_list.  If strict is true, all actors to be removed
        MUST be in the pk_list."""

        if not actors:
            logging.warning("empty list of actors passed to actorlist.remove_actors.")
            return

        if isinstance(actors[0], User):
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

        if isinstance(actors[0], int):
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
    """Helps deserialize actor list."""
    try:
        pk_list = json.loads(actor_list_string)
    except json.decoder.JSONDecodeError:
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
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return ActorList()
        return parse_actor_list_string(value)

    def to_python(self, value):
        if isinstance(value, ActorList):
            return value
        if value is None:
            return ActorList()
        if isinstance(value, list) and all([isinstance(x, int) for x in value]):
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


class RoleList(object):
    """Helper object to manage roles set in permission."""

    role_list = []

    def __init__(self, role_list=None):
        """Accepts a variety of formats, saves to role_list as a list of RolePair namedtuples."""
        self.role_list = role_list if role_list else []

    def is_empty(self):
        """Returns True if role_list is empty."""
        return False if self.role_list else True

    def get_roles(self):
        """Gets role list."""
        return self.role_list

    def role_name_in_list(self, role_name):
        """Returns true if given role_name in role list."""
        for role in self.role_list:
            if role_name == role:
                return True
        return False

    def add_roles(self, role_list):
        """Add roles to role_list."""
        role_set = set(self.role_list)
        for role in role_list:
            role_set.add(role)
        self.role_list = list(role_set)

    def remove_roles(self, role_list):
        """Remove roles from role_list."""
        role_set = set(self.role_list)
        for role in role_list:
            role_set.discard(role)
        self.role_list = list(role_set)


def parse_role_list_string(role_list_string):
    """Helper method to deserialize role list object."""
    try:
        role_list = json.loads(role_list_string)
    except json.decoder.JSONDecodeError:
        raise ValidationError("RoleListField was formatted wrongly and raised a JSONDecodeError")
    return RoleList(role_list=role_list)


class RoleListField(models.Field):
    """This custom field allows us to access our list of role pairs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return RoleList()
        return parse_role_list_string(value)

    def to_python(self, value):
        if isinstance(value, RoleList):
            return value
        if value is None:
            return RoleList()
        if isinstance(value, list) and all([isinstance(x, str) for x in value]):
            return RoleList(value)
        return parse_role_list_string(value)

    def get_prep_value(self, value):
        if isinstance(value, RoleList):
            return json.dumps(value.role_list)
        if value in [None, 'null', '[]']:
            return '[]'
