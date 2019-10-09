import json

from django.db import models
from django.contrib.auth.models import User

from concord.actions.models import PermissionedModel
from concord.conditionals.client import CommunityConditionalClient
from concord.communities.customfields import RoleHandler, RoleField


# TODO: put this somewhere more sensible (or maybe all this stringy stuff should go in templatetags)
def english_list(list_to_display):
    if len(list_to_display) <= 1:
        return "".join(list_to_display)
    return ", ".join(list_to_display[:-1]) + " and " + "".join(list_to_display[-1])

OWNER_CHOICES = (
    ('ind', 'Individually Owned'),
    ('com', 'Community Owned'),
)

################################
### Community Resource/Items ###
################################

class BaseCommunityModel(PermissionedModel):
    '''The base community model is the abstract type for all communities.  Much of its 
    logic is contained in customfields.RoleField and customfields.RoleHandler.'''

    is_community = True
    owner_type = models.CharField(max_length=3, choices=OWNER_CHOICES, 
        default='com')  # Community models are community-owned by default
    name = models.CharField(max_length=200)
    
    roles = RoleField(default=RoleHandler)

    class Meta:
        abstract = True

    def get_name(self):
        return self.name

    def get_owner(self):
        """
        Communities own themselves by default, unless they are subcommunities.
        """
        # BUG: this overwrites the get_owner on permissionedmodel, which doesn't seem ideal
        return self
    
    def owner_list_display(self):
        """
        Helper function to display results of list_owners() more nicely.
        """
        owners = self.list_owners()
        has_actors = 'actors' in owners and owners['actors']
        has_roles = 'roles' in owners and owners['roles']
        if has_actors and has_roles:
            return english_list(owners['actors']) + " and people in roles " + english_list(owners['roles'])
        if has_actors:
            return english_list(owners['actors'])
        if has_roles:
            return "people in roles " + english_list(owners['roles'])

    def governor_list_display(self):
        """
        Helper function to display results of list_governors() more nicely.
        """
        governors = self.list_governors()
        has_actors = 'actors' in governors and governors['actors']
        has_roles = 'roles' in governors and governors['roles']
        if has_actors and has_roles:
            return english_list(governors['actors']) + " and people in roles " + english_list(governors['roles'])
        if has_actors:
            return english_list(governors['actors'])
        if has_roles:
            return "people in roles " + english_list(governors['roles'])

    def owner_condition_display(self):
        comCondClient = CommunityConditionalClient(system=True, target=self)
        owner_condition = comCondClient.get_condition_info_for_owner()
        return owner_condition if owner_condition else "unconditional"

    def governor_condition_display(self):
        comCondClient = CommunityConditionalClient(system=True, target=self)
        governor_condition = comCondClient.get_condition_template_for_governor()
        return governor_condition if governor_condition else "unconditional"


class Community(BaseCommunityModel):
    """
    A community is, at heart, a collection of users.  Communities 
    govern resources that determine how these users interact, either
    moderating discussion spaces, like a community forum, setting
    restrictions on membership lists, or by setting access rules for
    resources owned by the community, such as saying only admins
    may edit data added to a dataset.
    """
    ...
    