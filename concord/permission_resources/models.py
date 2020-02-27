import json

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericRelation
from django.db.models.signals import post_save

from concord.actions.models import PermissionedModel
from concord.permission_resources.customfields import (ActorList, ActorListField, RoleList,
    RoleListField, TemplateDataField, TemplateData)


class PermissionsItem(PermissionedModel):
    """
    Permission items contain data for who may change the state of the linked object in a 
    given way.  

    content_type, object_id, permitted object -> specify what object the permission is set on
    change_type -> specifies what action the permission covers

    actors -> individually listed people
    roles -> reference to roles specified in community

    If someone matches an actor OR a role they have the permission. actors are checked first.
    """

    is_active = models.BooleanField(default=True)
    inverse = models.BooleanField(default=False)  # If toggled, applies to everyone BUT those listed in actors or roles
    # NOTE: may make sense to apply inverse to specific roles but too complex for now

    permitted_object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    permitted_object_id = models.PositiveIntegerField()
    permitted_object = GenericForeignKey('permitted_object_content_type', 'permitted_object_id')

    condition = GenericRelation("conditionals.ConditionTemplate", 
        object_id_field="conditioned_object_id", content_type_field='conditioned_object_content_type',
        related_query_name="permission")

    actors = ActorListField(default=ActorList) # Defaults to empty ActorList object  
    roles = RoleListField(default=RoleList) # Defaults to empty RoleList object

    change_type = models.CharField(max_length=200)  # Replace with choices field???
    configuration = models.CharField(max_length=5000, default='{}')

    # Get model-level information
    
    def get_name(self):
        return "Permission %s (for %s on %s)" % (str(self.pk), self.change_type, self.permitted_object)

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

    def get_change_type(self):
        return self.change_type.split(".")[-1]

    # Get misc info

    def get_target(self):
        # does this get used? what does it do?
        return self.resource.permitted_object

    def get_permitted_object(self):
        return self.permitted_object

    def get_condition(self):
        """Get condition set on permission"""
        from concord.conditionals.client import PermissionConditionalClient
        pcc = PermissionConditionalClient(system=True, target=self)
        return pcc.get_condition_template()

    # Get change type and configuration info (replace with customfield?)

    def short_change_type(self):
        return self.change_type.split(".")[-1]

    def match_change_type(self, change_type):
        return self.change_type == change_type

    def get_configuration(self):
        return json.loads(self.configuration) if self.configuration else {}

    def set_configuration(self, configuration_dict):
        self.configuration = json.dumps(configuration_dict)

    # Activation & deactivation

    def activate_permission(self):
        """For now, activate_permission is an internal method not accessible to the user which is 
        called via signals when a permission is updated to add actors or roles where before there 
        were none."""
        ...

    def deactivate_permission(self):
        """For now, activate_permission is an internal method not accessible to the user which is 
        called via signals when a permission is updated to remove all actors and roles."""
        ...
    
    # ActorList-related methods

    def get_actors(self, as_instances=False):
        if as_instances:
            return self.actors.as_instances()
        return self.actors.as_pks()

    def get_actor_names(self):
        return " ".join([user.username for user in self.actors.as_instances()])

    # RoleList-related methods

    def get_role_names(self):
        return self.roles.role_list

    def has_role(self, *, role: str):
        return self.roles.role_name_in_list(role_name=role)

    def add_role_to_permission(self, *, role: str):
        self.roles.add_roles(role_list=[role])

    def remove_role_from_permission(self, *, role: str):
        self.roles.remove_roles(role_list=[role])

    # Misc

    def match_actor(self, actor_pk):
        """Determines if actor in the permission.  If inverse is toggled, returns the oppposite -
        such that they would NOT match if they're listed in an inverse permission."""

        in_permission, matched_role = self.actor_in_permission(actor_pk)
        if self.inverse == True:
            matched_role = "" if not matched_role else "NOT " + matched_role
            return not in_permission, matched_role
        else:
            return in_permission, matched_role

    def actor_in_permission(self, actor):

        actors = self.get_actors()

        if actor.pk in actors:
            return True, None

        # FIXME: querying every role separately is a lot of lookups. create method to check if 
        # in any one of a subset of roles? 
        from concord.communities.client import CommunityClient
        cc = CommunityClient(system=True)
        for role in self.roles.get_roles():
            cc.set_target_community(community_pk=self.permitted_object.pk)
            if cc.has_role_in_community(role=role, actor_pk=actor.pk):
                return True, role

        return False, None


def delete_empty_permission(sender, instance, created, **kwargs):
    """Toggle is_active so it is only true when there are actors or roles set on the permission."""

    # Deactivate if empty
    if instance.actors.is_empty() and instance.roles.is_empty():
        if instance.is_active:
            instance.is_active = False
            instance.save(override_check=True)

    # Reactivate if has data
    if not instance.is_active:
        if not (instance.actors.is_empty() and instance.roles.is_empty()):
            instance.is_active = True
            instance.save(override_check=True)            


post_save.connect(delete_empty_permission, sender=PermissionsItem)


class Template(PermissionedModel):
    """ 
    Template models allow users to save and edit configurations of communities, owned objects,
    permissions, and conditionals.  New communities can be generated from these templates, making
    it easier for users to experiment with new governance structures.
    """
    data = TemplateDataField(null=True, default=TemplateData)
    description = models.CharField(max_length=500)