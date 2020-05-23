import json, collections

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from concord.permission_resources import templates


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
            else:
                raise ValidationError(message="actor_list must be User objects or pks, not " + str(type(first_item)))

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

        print("Actors: ", actors)
        
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


class RoleList(object):

    role_list = []

    def __init__(self, role_list=None):
        '''Accepts a variety of formats, saves to role_list as a list of RolePair namedtuples.'''
        self.role_list = role_list if role_list else []

    def is_empty(self):
        return False if self.role_list else True

    def get_roles(self):
        return self.role_list

    def role_name_in_list(self, role_name):
        for role in self.role_list:
            if role_name == role:
                return True
        return False

    def add_roles(self, role_list):
        role_set = set(self.role_list)
        for role in role_list:
            role_set.add(role)
        self.role_list = list(role_set)

    def remove_roles(self, role_list):
        role_set = set(self.role_list)
        for role in role_list:
            role_set.discard(role)
        self.role_list = list(role_set)


def parse_role_list_string(role_list_string):
    try:
        role_list = json.loads(role_list_string)
    except json.decoder.JSONDecodeError as error:
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
        if type(value) == list and all([type(x) == str for x in value]):
            return RoleList(value)
        return parse_role_list_string(value)

    def get_prep_value(self, value):
        if isinstance(value, RoleList):
            return json.dumps(value.role_list)
        if value in [None, 'null', '[]']:
            return '[]'


###################################
### TemplateData Object & Field ###
###################################


class TemplateData(object):

    def __init__(self):
        # need to create attributes on init because declaring them as model attributes (ie 
        # community = {} was somehow causing it to become a mutable default??)
        self.community = {}
        self.permissions = {}
        self.conditions = {}
        self.owned_objects = {}
        self.relationship_map = {}

    # display helpers

    def get_community(self):
        return list(self.community.values())[0]

    def get_permissions(self):
        return list(self.permissions.values())

    def get_conditions(self):
        return list(self.conditions.values())

    def get_owned_objects(self):
        return list(self.owned_objects.values())

    def get_combined_objects(self):
        return {**self.community, **self.permissions, **self.conditions, **self.owned_objects}

    def get_all_objects(self):
        return list(self.get_combined_objects().values())

    def get_target_of_field(self, item_id, field_name):
        target_id = None
        for related_field in self.relationship_map["related_fields"]:
            if related_field["name"] == field_name and related_field["field_on"] == int(item_id):
                target_id = str(related_field["field_target_id"])
        try:
            return self.get_combined_objects()[target_id]
        except:
            pass
        try:
            return self.get_combined_objects()[int(target_id)]
        except:
            pass

    def is_editable_field(self, field):
        """We currently allow only simple non-related fields to be edited, but eventually all fields
        should be editable."""
        # '"_id" in field.name' is a bit of a hack to identify positive integer fields used in gfks
        if field.is_relation or field.auto_created or "_id" in field.name or "condition_data" == field.name:
            return False
        return True

    def get_editable_field_value(self, item, field):
        # FIXME: this is not the best place for this logic :/
        field_value = getattr(item, field.name)
        if field.__class__.__name__ == "RoleListField":  # permission's RoleList custom field
            return field_value.get_roles()
        if field.__class__.__name__ == "ActorListField":  # permission's ActorList custom field
            return field_value.as_pks()
        if field.__class__.__name__ == "RoleField":  # community's Role custom field
            return field_value.get_roles()  
        return field_value

    def get_editable_fields(self):
        """       
        Return list with dicts corresponding to each field:
        { 'object_id': X, 'object_model': Y, 'field_name': Z, 'field_value': Q }
        """
        editable_fields = []
        for item_key, item in self.get_combined_objects().items():
            fields = item._meta.get_fields()
            for field in fields:
                if self.is_editable_field(field):
                    editable_fields.append({
                        "template_object_id": item_key,  # useful for updating fields
                        "object_model": str(item._meta.model.__name__),   # for user display
                        "field_name": field.name,
                        "field_value": self.get_editable_field_value(item, field)
                    })
        return editable_fields

    # manipulate data

    def create_template(self, community=None, permissions=None, conditions=None, owned_objects=None,
        recursive=False):
        """Creates TemplateData object.  Only used when actually creating the template for the
        first time - when instantiating from database, we create an empty object and load manually.
        Generate_relationship_map assumes real objects with database IDs."""
        # FIXME: the fact that community is an item while the other three are lists is something we
        # should not need the end user to know

        id_count = 0

        if community:
            id_count += 1
            self.community = { id_count : community }
            if recursive:
                id_count = self.get_recursive_data_for_template(id_count)

        if permissions:
            for permission in permissions:
                id_count += 1
                self.permissions.update({ id_count : permission })

        if conditions:
            for condition in conditions:
                id_count += 1
                self.conditions.update({ id_count : condition })
            
        if owned_objects:
            for owned_object in owned_objects:
                id_count += 1
                self.owned_objects.update({ id_count: owned_object })

        if community or permissions or conditions or owned_objects:
            self.generate_relationship_map()

    def get_recursive_data_for_template(self, id_count):
        """Called when we have a community and recursive=True, gets all permissions and conditions
        related to the community and any owned objects also passed in."""

        from concord.permission_resources.client import PermissionResourceClient
        from concord.conditionals.client import CommunityConditionalClient, PermissionConditionalClient
        permissionClient = PermissionResourceClient(actor="system")
        commConditionalClient = CommunityConditionalClient(actor="system")
        permConditionalClient = PermissionConditionalClient(actor="system")

        objects_to_check = [self.get_community()] + self.get_owned_objects()

        while len(objects_to_check) > 0:
        
            current_object = objects_to_check.pop(0) 

            # Check permission
            permissions = permissionClient.get_permissions_on_object(object=current_object)
            for permission in permissions:
                id_count += 1
                self.permissions.update({ id_count : permission })
                objects_to_check.append(permission)

            condition_templates = []
            # Check for conditionals set on it
            if current_object.__class__.__name__ == "Community":
                commConditionalClient.set_target(target=current_object)
                govConditionTemplate = commConditionalClient.get_condition_template_for_governor()
                ownerConditionTemplate = commConditionalClient.get_condition_template_for_owner()
                condition_templates.append(govConditionTemplate, ownerConditionTemplate)
            elif current_object.__class__.__name__ == "PermissionsItem":
                permConditionalClient.set_target(target=current_object)
                conditionTemplate = permConditionalClient.get_condition_template()
                condition_templates.append(conditionTemplate)
            for condition in condition_templates:
                if condition:
                    id_count += 1
                    self.conditions.update({ id_count : condition })
                    objects_to_check.append(condition)

    def is_saveable_related_field(self, field):
        """This method indicates whether the given field is (a) a related field and (b) a related
        field we want to save - for instance, we do not save generic relations or reverse relations, nor
        do we save the individual elements of a generic foreign key (content type and ID fields it 
        references)."""
        if field.is_relation:
            if field.__class__.__name__ not in ["GenericRel", "GenericRelation", "ManyToOneRel", "ManyToOneRelation"]:
                if "ContentType" not in str(field.related_model):  # capitalization is important here
                    return True
        return False

    def generate_relationship_map(self):
        """
        Generates a list of dicts with four keys: name, field_on (new ID of model field is on),
            field_target (new ID of model field is targetting)

        FIXME: how do we handle related fields pointing outside of this set?  currently we handle 
        owner with check_ownership but that's it
        """

        # go through all_objects and genereate a old_db_id : template_id pair
        pair_map = {}
        all_objects = {**self.community, **self.permissions, **self.conditions, **self.owned_objects}
        for item_key, item in all_objects.items():
            pair_map.update({ str(item.pk) + "_" + item._meta.model.__name__ : item_key })   

        # go through all_objects and map related fields
        related_fields = []
        for item_key, item in all_objects.items():
            fields = item._meta.get_fields()
            for field in fields:
                # skip owner field for community only
                if hasattr(item, "is_community") and item.is_community:
                    if field.name == "owner":
                        continue
                # if the field is a related field and its value is not None, store data
                if self.is_saveable_related_field(field) and getattr(item, field.name) is not None: 
                    new_key = str(item.pk) + "_" + item._meta.model.__name__
                    field_dict = { "name": field.name, "field_on": pair_map[new_key] }
                    if hasattr(field, "get_content_type"):  # if field is generic foreign key
                        target_model = getattr(item, field.ct_field).model_class()
                        new_key = str(getattr(item, field.fk_field)) + "_" + target_model.__name__
                        field_dict["field_target_id"] = pair_map[new_key]
                        field_dict["field_target_ct"] = getattr(item, field.ct_field).pk
                    else:
                        new_key = str(field.value_from_object(item)) + "_" + field.related_model.__name__
                        field_dict["field_target_id"] = pair_map[new_key]
                    related_fields.append(field_dict)

        # save related_fields as relationship map
        self.relationship_map.update({"related_fields": related_fields})

    def update_related_field(self, pair_map, current_object, current_object_new_id, field):
        """Given a model (current_object) and field, update the field to point to the item listed in 
        relationship_map or return false if no match found."""
        for rf in self.relationship_map["related_fields"]:
            if rf["name"] == field.name and rf["field_on"] == int(current_object_new_id):
                target_id = str(rf["field_target_id"])
                if pair_map[target_id]["switched"] == True:
                    # If referenced object is ready, set field
                    setattr(current_object, field.name, pair_map[target_id]["object"])
                    return True, current_object
        return False, None

    def check_related_fields(self, pair_map, current_object_new_id, current_object, default_owner, 
        default_community):
        """Helper function, checks related fields on an object to see if all data is in 
        relationship map.  If all related fields in the map, returns True & the updated object,
        otherwise returns False & None."""

        fields = current_object._meta.get_fields()
        for field in fields:
            if self.is_saveable_related_field(field):
                if field.name == "owner":
                    current_object = self.check_ownership(current_object, default_owner, default_community)
                else:
                    object_updated, current_object = self.update_related_field(pair_map, current_object, 
                        current_object_new_id, field)
                    if not object_updated:
                        return False, None  # If something returned not updated, need to skip obj for now
        return True, current_object

    def check_ownership(self, current_object, default_owner, default_community):
        """All objects except communities need an owner.  Templates may assign ownership but most
        will assume the person who created them as the owner."""
        # FIXME: may be fixable by passing this info to check_related_fields

        if current_object.__class__.__name__ == "Community":
            return current_object

        if current_object.get_owner() == None:
            if default_community:
                current_object.owner = default_community
            elif default_owner:
                current_object.owner = default_owner
            else:
                raise Exception("Must provide default owner or default community for object", current_object)

        return current_object

    def create_from_template(self, default_owner=None):

        # go through objects_to_create and make a map with template_id as key and None as value
        pair_map = {}
        objects_to_create = collections.OrderedDict({**self.community, **self.permissions, 
            **self.conditions, **self.owned_objects})
        for item_key, item in objects_to_create.items():
            pair_map.update({ item_key : { "object": item, "switched": False } })

        default_community = self.community.popitem()[1] if self.community else None

        created_objects = []
        # go through objects to create, adding them as the values in the template_id pair as you go
        while len(objects_to_create) > 0:

            current_object_dict = objects_to_create.popitem(last=False)
            current_object_new_id, current_object = current_object_dict[0], current_object_dict[1]

            fields_ready, current_object = self.check_related_fields(pair_map, current_object_new_id, 
                current_object, default_owner, default_community)

            if fields_ready:
                current_object.save()
                created_objects.append(current_object)
                pair_map[current_object_new_id]["object"] = current_object
                pair_map[current_object_new_id]["switched"] = True
            else:
                objects_to_create.update({ current_object_dict[0]: current_object_dict[1] })

        return created_objects

        # possibly need to refresh templatedata object so the items are not pointing at the newly
        # created objects?  how to check this?

    def generate_text(self):
        return templates.generate_text_from_template(template_model=self)

    def reformat_data(self, field_object, new_field_data):
        """Fixes format issues for custom fields, corresponds to get_editable_field_value
        # FIXME: also not the best place for this logic"""

        if field_object.__class__.__name__ == "RoleListField":  # permission's RoleList custom field
            try:
                return RoleList(role_list=new_field_data)
            except:
                raise ValidationError("Data supplied (%s) is incorrectly formatted for RoleList field" % new_field_data)
        if field_object.__class__.__name__ == "ActorListField":  # permission's ActorList custom field
            try:
                return ActorList(actor_list=new_field_data)
            except:
                raise ValidationError("Data supplied (%s) is incorrectly formatted for ActorList field" % new_field_data)
        if field_object.__class__.__name__ == "RoleField":  # community's Role custom field
            try:
                from concord.communities.customfields import RoleHandler
                reformatted_data = RoleHandler().reformat_flat_roles(new_field_data)
                return RoleHandler(**reformatted_data)
            except:
                raise ValidationError("Data supplied (%s) is incorrectly formatted for RoleHandler field" % new_field_data)
        return new_field_data

    def update_field(self, template_object_id, field_name, new_field_data):
        """ Updates a field with new data, created to be called by front-ends.
        
        TODO: need to better understand Django model field validation and add validators such
        that we can rely on the clea() call to handle validation here.
        """

        object_to_update = self.get_combined_objects()[template_object_id]

        # reformat data if needed
        try:
            field_object = object_to_update._meta.get_field(field_name)
            new_field_data = self.reformat_data(field_object, new_field_data)
            setattr(object_to_update, field_name, new_field_data)
        except ValidationError as VE:
            return VE

        # Validate data and save
        try:
            value_to_test = getattr(object_to_update, field_name)
            result = field_object.clean(value_to_test, object_to_update)  
            return result
        except ValidationError as VE:
            return VE


# Helper methods for TemplateDataField


def parse_template_data(saved_data):

    saved_data = json.loads(saved_data)
    template_data = TemplateData()
    
    # load community
    for community_key, community in saved_data["community"].items():  # should be only one!
        template_data.community = { community_key: 
            templates.create_unsaved_instance_given_template(community) }

    # load permissions
    for permission_key, permission in saved_data["permissions"].items():
        template_data.permissions.update({ permission_key : 
            templates.create_unsaved_instance_given_template(permission)})
    
    # load conditions
    for condition_key, condition in saved_data["conditions"].items():
        template_data.conditions.update({ condition_key : 
            templates.create_unsaved_instance_given_template(condition)})

    # load owned objects
    for obj_key, obj in saved_data["owned_objects"].items():
        template_data.owned_objects.update({ obj_key : 
            templates.create_unsaved_instance_given_template(obj)})    
    
    template_data.relationship_map = saved_data["relationship_map"]
    
    return template_data


def save_template_data(object_to_save):
    """Converts templatedata field into json-serializable dict."""

    save_dict = { "community": {}, "permissions": {}, "conditions": {}, "owned_objects": {},
        "relationship_map": object_to_save.relationship_map }  

    # save community
    for community_key, community in object_to_save.community.items():  # should be only one!
        save_dict["community"] = { community_key: templates.json_serializable_community(community) }

    # save permissions
    for permission_key, permission in object_to_save.permissions.items():
        save_dict["permissions"].update({ permission_key : 
            templates.json_serializable_permission(permission) })
    
    # save conditions
    for condition_key, condition in object_to_save.conditions.items():
        save_dict["conditions"].update({ condition_key : 
            templates.json_serializable_condition(condition)})

    # save owned objects
    for obj_key, obj in object_to_save.owned_objects.items():
        save_dict["owned_objects"].update({ obj_key : 
            templates.json_serializable_object(obj)})

    return json.dumps(save_dict)


class TemplateDataField(models.Field):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'  

    def from_db_value(self, value, expression, connection):
        if value is None:
            return TemplateData()
        return parse_template_data(value)

    def to_python(self, value):
        if isinstance(value, TemplateData):
            return value
        if value is None:
            return TemplateData()
        return parse_template_data(value)

    def get_prep_value(self, value):
        if isinstance(value, TemplateData):
            return save_template_data(value)
        if value in [None, 'null', '[]']:
            return '[]'   # This seems wrong
