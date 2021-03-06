"""Permission Resource models."""

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save

from concord.actions.models import PermissionedModel
from concord.permission_resources.customfields import ActorList, ActorListField, RoleList, RoleListField
from concord.utils.text_utils import permission_to_text, permission_change_to_text
from concord.utils.helpers import Client
from concord.utils.lookups import get_state_change_object


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

    condition = models.ForeignKey('conditionals.ConditionManager', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="%(app_label)s_%(class)s_conditioned")

    actors = ActorListField(default=ActorList)  # Defaults to empty ActorList object
    roles = RoleListField(default=RoleList)  # Defaults to empty RoleList object
    anyone = models.BooleanField(default=False)

    change_type = models.CharField(max_length=200)  # Replace with choices field???

    # Get model-level information

    def __str__(self):
        return self.get_name()

    def get_name(self):
        """Get permission name."""
        return f"Permission {self.pk} ({self.get_change_type()} on {self.permitted_object})"

    def display_string(self):
        """Helper method for displaying permissions."""
        return permission_to_text(self)

    def change_display_string(self):
        """Helper method for displaying the change element of permissions."""
        return permission_change_to_text(self)

    def change_name(self):
        return self.get_state_change_object().change_description(capitalize=False)

    def get_change_type(self):
        """Get the ChangeType (short version) of the permission."""
        return self.change_type.split(".")[-1]

    def get_context_keys(self):
        """Helper method to get context keys for the change type."""
        return self.get_state_change_object().get_context_keys()

    def get_change_fields(self):
        """Helper method used to get a list of required fields for init of this permission's change
        type."""
        return self.get_state_change_object().get_change_field_options()

    def set_fields(self, *, owner=None, permitted_object=None, anyone=None, change_type=None, inverse=None,
                   actors=None, roles=None):
        """Helper method to make it easier to save permissions fields in the format our model expects."""

        self.owner = owner if owner else self.owner
        self.permitted_object = permitted_object if permitted_object else self.permitted_object
        self.anyone = anyone if anyone else self.anyone
        self.change_type = change_type if change_type else self.change_type
        self.inverse = inverse if inverse else self.inverse

        if actors:
            try:
                self.actors.add_actors(actors=actors)
            except ValueError:
                self.actors = actors

        if roles:
            try:
                self.roles.add_roles(role_list=roles)
            except ValueError:
                self.roles = roles

    # Get misc info

    def has_condition(self):
        """Returns True if PermissionsItem has condition, otherwise False."""
        return bool(self.condition)

    def get_condition_data(self):
        """Used in forms."""
        if self.condition:
            return self.condition.get_condition_form_data(permission=self)
        return {}

    def get_permitted_object(self):
        """Gets the permitted object, that is the permissioned model that the permission is set on."""
        return self.permitted_object

    def get_state_change_object(self):
        """Get the state change object associated with the change_type of the permission."""
        return get_state_change_object(self.change_type)

    def get_section(self):
        return self.get_state_change_object().section

    def is_foundational(self):
        return self.get_state_change_object().is_foundational

    def match_change_type(self, change_type):
        """Checks if the given change type matches the PermissionItem's change_type."""
        return self.change_type == change_type

    # ActorList and RoleList related methods

    def get_actors(self, as_instances=False):
        """Get the actors that have the permission."""
        if as_instances:
            return self.actors.as_instances()
        return self.actors.as_pks()

    def get_roles(self):
        """Get the roles that have the permission."""
        return self.roles.role_list

    def has_role(self, *, role: str):
        """Check if a given role has the permission."""
        return self.roles.role_name_in_list(role_name=role)

    def add_role_to_permission(self, *, role: str):
        """Add a role to the permission."""
        self.roles.add_roles(role_list=[role])

    def remove_role_from_permission(self, *, role: str):
        """Remove a role from the permission."""
        self.roles.remove_roles(role_list=[role])

    # Misc

    def match_actor(self, actor_pk):
        """Determines if actor in the permission.  If inverse is toggled, returns the oppposite -
        such that they would NOT match if they're listed in an inverse permission."""

        if self.anyone:
            return True, "anyone"

        in_permission, matched_role = self.actor_in_permission(actor_pk)
        if self.inverse is True:
            matched_role = "" if not matched_role else "NOT " + matched_role
            return not in_permission, matched_role
        else:
            return in_permission, matched_role

    def actor_in_permission(self, actor):
        """Check if actor is in the permission, either as individual or as role.  Returns Boolean plus the role
        if in permission via role, otherwise returns None."""

        actors = self.get_actors()

        if actor.pk in actors:
            return True, None

        community_owning_permitted_object = self.permitted_object.get_owner()

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
    if instance.actors.is_empty() and instance.roles.is_empty() and instance.anyone is False:
        if instance.is_active:
            instance.is_active = False
            instance.save(override_check=True)

    # Reactivate if has data
    if not instance.is_active:
        if not (instance.actors.is_empty() and instance.roles.is_empty() and instance.anyone is False):
            instance.is_active = True
            instance.save(override_check=True)


post_save.connect(delete_empty_permission, sender=PermissionsItem)
