import json

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from concord.actions.models import PermissionedModel
from concord.permission_resources.utils import check_permission_inputs


# Create your models here.
class PermissionsResource(PermissionedModel):

    # For now just using inbuilt generic relation, but may want to switch???
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    permitted_object = GenericForeignKey('content_type', 'object_id')
    ignore_defaults = models.BooleanField(default=False)

    # Basics

    def get_name(self):
        return "Permissions resource for " + self.permitted_object.get_name()

    # Read-only

    # FIXME: I don't think the permissions items are actually linking to the PR, and therefore
    # I don't think self.permissionsitem_set.all will work.  But this isn't being called/tested
    # anywhere.
    def get_items(self):
        result = []
        for item in self.permissionsitem_set.all():
            result.append(item.get_name())
        return result


class PermissionsItem(PermissionedModel):
    """
    Permission items contain data for who may change the state of the linked object in a 
    given way.  

    content_type, object_id, permitted object -> specify what object the permission is set on
    change_type -> specifies what action the permission covers

    actors -> individually listed people
    roles -> reference to roleset specified in community

    if someone matches an actor OR a role they have the permission. actors are checked first.

    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    permitted_object = GenericForeignKey('content_type', 'object_id')

    # FIXME: both actors & roles are list of strings saved as json, need to be custom field
    actors = models.CharField(max_length=200)  
    roles = models.CharField(max_length=500)

    change_type = models.CharField(max_length=200)  # Replace with choices field???
    configuration = models.CharField(max_length=5000, default='{}')

    def get_name(self):
        return "Permission %s (for %s on %s)" % (str(self.pk), self.change_type, self.permitted_object)

    def get_permitted_object(self):
        return self.permitted_object

    def display_string(self):
        display_string = ""
        actor_names = self.get_actors()
        role_names = self.get_role_names()
        if actor_names:
            display_string += "individuals " + actor_names
        if actor_names and role_names:
            display_string += " and "
        if role_names:
            display_string += "those with roles " + role_names
        display_string += " have permission to " + self.change_type.split(".")[-1]
        return display_string

    # Permissions-specific helpers

    def get_condition(self):
        from concord.conditionals.client import PermissionConditionalClient
        pcc = PermissionConditionalClient(actor="system", target=self)
        return pcc.get_condition_template()

    def get_target(self):
        return self.resource.permitted_object

    def short_change_type(self):
        return self.change_type.split(".")[-1]

    def match_change_type(self, change_type):
        return self.change_type == change_type

    def get_configuration(self):
        return json.loads(self.configuration) if self.configuration else {}

    def set_configuration(self, configuration_dict):
        self.configuration = json.dumps(configuration_dict)
        
    def get_actors(self):
        return json.loads(self.actors) if self.actors else []

    def get_roles(self):
        return json.loads(self.roles) if self.roles else []

    def get_actor_names(self):
        if self.get_actors():
            return " ".join(self.get_actors())
        return ""

    # NOTE: I'm using this method with the assumption that all roles 
    # are from the same community, which may not always be true.
    def get_role_names(self):
        role_pairs = self.get_roles()
        role_names = []
        for role_pair in role_pairs:
            community, role_name = role_pair.split("_")
            role_names.append(role_name)
        return role_names

    def match_actor(self, actor):

        actors = self.get_actors()
        if actor in actors:
            return True, None

        role_pairs = self.get_roles()  # FIXME: "role_pair" is not super descriptive
        from concord.communities.client import CommunityClient
        cc = CommunityClient(actor="system")
        for pair in role_pairs:
            community_pk, role = pair.split("_")  # FIXME: bit hacky
            cc.set_target_community(community_pk=community_pk)
            if cc.has_role_in_community(role=role, actor=actor):
                return True, pair

        # TODO: thing the above through.  If every role is queried separately, that's a lot of 
        # lookups.  You could provide the roles to each community in bulk?

        return False, None

    # Write stuff called by statechanges

    @check_permission_inputs(dict_of_inputs={'actor': 'simple_string'})
    def add_actor_to_permission(self, *, actor: str):
        actors = self.get_actors()
        if actor not in actors:
            actors.append(actor)
            self.actors = json.dumps(actors)
        else:
            print("Actor ", actor, " already in permission item actors")
    
    @check_permission_inputs(dict_of_inputs={'actor': 'simple_string'})
    def remove_actor_from_permission(self, *, actor: str):
        actors = self.get_actors()
        if actor in actors:
            actors.remove(actor)
            self.actors = json.dumps(actors)
        else:
            print("Actor ", actor, " not in permission item actors")

    @check_permission_inputs(dict_of_inputs={'role': 'simple_string', 'community': 'string_pk'})
    def add_role_to_permission(self, *, role: str, community: str):
        new_pair = community + "_" + role
        role_pairs = self.get_roles()
        if new_pair not in role_pairs:
            role_pairs.append(new_pair)
            self.roles = json.dumps(role_pairs)
        else:
            print("Role pair to add, ", new_pair, ", is already in permission item roles")

    @check_permission_inputs(dict_of_inputs={'role': 'simple_string', 'community': 'string_pk'})
    def remove_role_from_permission(self, *, role: str, community: str):
        pair_to_delete = community + "_" + role
        role_pairs = self.get_roles()
        if pair_to_delete in role_pairs:
            role_pairs.remove(pair_to_delete)
            self.roles = json.dumps(role_pairs)
        else:
            print("Role pair to delete, ", pair_to_delete, ", is not in permission item roles")

    @check_permission_inputs(dict_of_inputs={'role_pair_to_add': 'role_pair'})
    def add_role_pair_to_permission(self, *, role_pair_to_add: str):
        role_pairs = self.get_roles()
        if role_pair_to_add not in role_pairs:
            role_pairs.append(role_pair_to_add)
            self.roles = json.dumps(role_pairs)
        else:
            print("Role pair to add, ", role_pair_to_add, ", is already in permission item roles")

    @check_permission_inputs(dict_of_inputs={'role_pair_to_remove': 'role_pair'})
    def remove_role_pair_from_permission(self, *, role_pair_to_remove: str):
        role_pairs = self.get_roles()
        if role_pair_to_remove in role_pairs:
            role_pairs.remove(role_pair_to_remove)
            self.roles = json.dumps(role_pairs)
        else:
            print("Role pair to delete, ", role_pair_to_remove, ", is not in permission item roles")

