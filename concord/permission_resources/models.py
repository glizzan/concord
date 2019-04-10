import json

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from concord.actions.models import PermissionedModel


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

    actors = models.CharField(max_length=200)  # Replace with user model link
    roles = models.CharField(max_length=500)

    change_type = models.CharField(max_length=200)  # Replace with choices field???

    def get_name(self):
        return "Permission %s (for %s on %s)" % (str(self.pk), self.change_type, self.permitted_object)

    # Permissions-specific helpers

    def get_target(self):
        return self.resource.permitted_object

    def match_change_type(self, change_type):
        return self.change_type == change_type

    def get_actors(self):
        return json.loads(self.actors) if self.actors else []

    def get_roles(self):
        return json.loads(self.roles) if self.roles else []

    def match_actor(self, actor):

        actors = self.get_actors()
        if actor in actors:
            return True

        role_pairs = self.get_roles()
        from concord.communities.client import CommunityClient
        cc = CommunityClient(actor="system")
        for pair in role_pairs:
            community, role = pair.split("_")  # FIXME: bit hacky
            result = cc.has_role_in_community(community_pk=community, role=role, actor=actor)
            if result:
                return True

        # TODO: thing the above through.  If every role is queried separately, that's a lot of 
        # lookups.  You could provide the roles to each community in bulk?

        return False

    # Write stuff called by statechanges

    def add_actor_to_permission(self, actor):
        actors = self.get_actors()
        if actor not in actors:
            actors.append(actor)
            self.actors = json.dumps(actors)
        else:
            print("Actor ", actor, " already in permission item actors")
    
    def remove_actor_from_permission(self, actor):
        actors = self.get_actors()
        if actor in actors:
            actors.remove(actor)
            self.actors = json.dumps(self.actors)
        else:
            print("Actor ", actor, " not in permission item actors")
    
    def add_role_to_permission(self, role, community):
        new_pair = community + "_" + role
        role_pairs = self.get_roles()
        if new_pair not in role_pairs:
            role_pairs.append(new_pair)
            self.roles = json.dumps(role_pairs)
        else:
            print("Role pair to add, ", new_pair, ", is already in permission item roles")

    def remove_role_from_permission(self, role, community):
        pair_to_delete = community + "_" + role
        role_pairs = self.get_roles()
        if pair_to_delete in role_pairs:
            role_pairs.remove(pair_to_delete)
            self.roles = json.dumps(role_pairs)
        else:
            print("Role pair to delete, ", pair_to_delete, ", is not in permission item roles")
