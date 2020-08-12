import json

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericRelation
from django.db.models.signals import post_save

from concord.actions.models import PermissionedModel
from concord.actions.customfields import Template, TemplateField
from concord.permission_resources.customfields import ActorList, ActorListField, RoleList, RoleListField
from concord.actions.text_utils import permission_to_text, permission_change_to_text


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

    permitted_object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    permitted_object_id = models.PositiveIntegerField()
    permitted_object = GenericForeignKey('permitted_object_content_type', 'permitted_object_id')

    condition = TemplateField(default=Template, system=True)   # Defaults to empty Template object

    actors = ActorListField(default=ActorList) # Defaults to empty ActorList object  
    roles = RoleListField(default=RoleList) # Defaults to empty RoleList object
    anyone = models.BooleanField(default=False)

    change_type = models.CharField(max_length=200)  # Replace with choices field???
    configuration = models.CharField(max_length=5000, default='{}')

    # Get model-level information
    
    def get_name(self):
        return "Permission %s (for %s on %s)" % (str(self.pk), self.change_type, self.permitted_object)

    def display_string(self):
        """Helper method for displaying permissions."""
        return permission_to_text(self)

    def change_display_string(self):
        """Helper method for displaying the change element of permissions."""
        return permission_change_to_text(self)

    def get_change_type(self):
        return self.change_type.split(".")[-1]

    def set_fields(self, *, owner=None, permitted_object=None, anyone=None, change_type=None, inverse=None, 
                   actors=None, roles=None, configuration=None):
        """Helper method to make it easier to save permissions fields in the format our model expects."""

        self.owner = owner if owner else self.owner
        self.permitted_object = permitted_object if permitted_object else self.permitted_object
        self.anyone = anyone if anyone else self.anyone
        self.change_type = change_type if change_type else self.change_type
        self.inverse = inverse if inverse else self.inverse

        if actors:
            self.actors.add_actors(actors=actors)
        if roles:
            self.roles.add_roles(role_list=roles)
        
        if configuration:
            configuration_dict = {key: value for key, value in configuration.items() if value not in [None, [], ""]}
            self.set_configuration(configuration_dict)

    # Get misc info

    def has_condition(self):
        if self.condition and self.condition.has_template():
            return True
        return False  

    def get_condition_data(self, info="all"):
        """Uses the change data saved in the mock actions to instantiate the condition and permissions
        that will be created and get their info, to be used in forms"""
        from concord.conditionals.utils import generate_condition_form_from_action_list
        return generate_condition_form_from_action_list(self.condition.action_list, info)

    def get_permitted_object(self):
        return self.permitted_object

    def get_state_change_object(self):
        from concord.actions.utils import get_state_change_object
        return get_state_change_object(self.change_type)

    # Get change type and configuration info (replace with customfield?)

    def match_change_type(self, change_type):
        return self.change_type == change_type

    def get_configuration(self):
        return json.loads(self.configuration) if self.configuration else {}

    def set_configuration(self, configuration_dict):
        self.configuration = json.dumps(configuration_dict)

    def get_configured_field_data(self):
        # Returns (possibly empty) dict with format { permissionfieldname : permissionfieldvalue }
        return self.get_configuration()  # is it this simple?

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
    
    # ActorList and RoleList related methods

    def get_actors(self, as_instances=False):
        if as_instances:
            return self.actors.as_instances()
        return self.actors.as_pks()

    def get_roles(self):
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

        if self.anyone:
            return True, "anyone"

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

        community_owning_permitted_object = self.permitted_object.get_owner()

        from concord.actions.utils import Client
        client = Client(target=community_owning_permitted_object)
        
        for role in self.roles.get_roles():
            if client.Community.has_role_in_community(role=role, actor_pk=actor.pk):
                return True, role

        return False, None

    def get_nested_objects(self):
        return [self.get_owner(), self.permitted_object]


def delete_empty_permission(sender, instance, created, **kwargs):
    """Toggle is_active so it is only true when there are actors or roles set on the permission."""

    # Deactivate if empty
    if instance.actors.is_empty() and instance.roles.is_empty() and instance.anyone == False:
        if instance.is_active:
            instance.is_active = False
            instance.save(override_check=True)

    # Reactivate if has data
    if not instance.is_active:
        if not (instance.actors.is_empty() and instance.roles.is_empty() and instance.anyone == False):
            instance.is_active = True
            instance.save(override_check=True)            


post_save.connect(delete_empty_permission, sender=PermissionsItem)
