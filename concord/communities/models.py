"""Models for Community package."""

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save

from concord.actions.models import PermissionedModel
from concord.communities.customfields import RoleHandler, RoleField
from concord.actions.customfields import TemplateField, Template
from concord.conditionals.utils import generate_condition_form_from_action_list


################################
### Community Resource/Items ###
################################

class BaseCommunityModel(PermissionedModel):
    """The base community model is the abstract type for all communities.  Much of its
    logic is contained in customfields.RoleField and customfields.RoleHandler."""
    is_community = True

    name = models.CharField(max_length=200)
    roles = RoleField(default=RoleHandler)

    owner_condition = TemplateField(default=Template, system=True)
    governor_condition = TemplateField(default=Template, system=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return f"CommunityModel(pk={self.pk}, name={self.name}, roles={self.roles}, " + \
               f"owner_condition={self.has_condition('owner')}, governor_condition={self.has_condition('governor')}"

    def get_name(self):
        """Get name of community."""
        return self.__str__()

    def get_owner(self):
        """Communities own themselves by default, although subtypes may differ."""
        return self

    def has_condition(self, leadership_type):
        """Returns True if community has a condition set on owner or on governor, depending on the leadership_type
        passed in."""
        if leadership_type == "owner":
            return self.has_owner_condition()
        elif leadership_type == "governor":
            return self.has_governor_condition()

    def get_condition(self, leadership_type):
        """Gets the condition set on the leadership type specified."""
        if leadership_type == "owner":
            return self.owner_condition
        elif leadership_type == "governor":
            return self.governor_condition

    def has_owner_condition(self):
        """Returns True if community has an owner condition, False if not."""
        if self.owner_condition and self.owner_condition.has_template():
            return True
        return False

    def has_governor_condition(self):
        """Returns True if community has a governor condition, False if not."""
        if self.governor_condition and self.governor_condition.has_template():
            return True
        return False

    def get_condition_data(self, leadership_type, info="all"):
        """Uses the change data saved in the mock actions to instantiate the condition and permissions
        that will be created and get their info, to be used in forms"""

        if leadership_type == "owner" and self.has_owner_condition():
            action_list = self.owner_condition.action_list
        elif leadership_type == "governor" and self.has_governor_condition():
            action_list = self.governor_condition.action_list
        else:
            return

        return generate_condition_form_from_action_list(action_list, info)


class Community(BaseCommunityModel):
    """A community is, at heart, a collection of users.  Communities govern resources that determine
    how these users interact, either moderating discussion spaces, like a community forum, setting
    restrictions on membership lists, or by setting access rules for resources owned by the community,
    such as saying only admins may edit data added to a dataset."""
    ...


class DefaultCommunity(BaseCommunityModel):
    """Every user has a default community of which they are the BDFL.  (They can
    theoretically give someone else power over their default community, but we should
    probably prevent that on the backend.)

    We're almost always accessing this through the related_name.  We have the user, and
    we want to know what community to stick our object in."""
    user_owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="default_community")


def create_default_community(sender, instance, created, **kwargs):
    """Creates default community for a user when a new user is created."""
    if created:
        name = f"{instance.username}'s Default Community"
        roles = RoleHandler()
        roles.initialize_with_creator(creator=instance.pk)
        DefaultCommunity.objects.create(name=name, user_owner=instance, roles=roles)


post_save.connect(create_default_community, sender=User)
