"""Client for Community models."""

import logging

from django.db.models import Model
from django.contrib.auth.models import User

from concord.actions.client import BaseClient
from concord.utils.text_utils import community_basic_info_to_text, community_governance_info_to_text
from concord.communities.models import Community
from concord.communities.customfields import RoleHandler


logger = logging.getLogger(__name__)


######################
### CommunityClient ###
######################

class CommunityClient(BaseClient):
    """The target of a community client, if a target is required, is always a community model. As with all
    Concord clients, a target must be set for all methods not explicitly grouped as target-less methods."""
    app_name = "communities"

    community_model = Community

    def set_target(self, target):
        super().set_target(target)
        if not hasattr(target, "is_community"):
            logging.debug("Target of CommunityClient must be a Community model")
        self.community_model = self.target.__class__

    # Target-less methods (don't require a target to be set ahead of time)

    def set_target_community(self, *, community_name: str = None, community_pk: str = None):
        """Sets target community given a name or pk. If the user already has the community object,
        it can be set directly using the parent method set_target."""
        self.target = self.get_community(community_name=community_name, community_pk=community_pk)

    def get_community(self, *, community_name: str = None, community_pk: str = None) -> Community:
        """Takes either community name or PK and returns Community object.  If both are supplied,
        returns Community object corresponding to community_pk."""
        if community_pk:
            return self.community_model.objects.get(pk=community_pk)
        if community_name:
            return self.community_model.objects.get(name=community_name)
        raise Exception("Get community require community name or community pk")

    def get_communities(self):
        """Gets all communities with the model type specified on the client."""
        return self.community_model.objects.all()

    def get_communities_for_user(self, user_pk, split=False):
        """Given a supplied user_pk, gets all communities the associated user is a part of.  If arg 'split' is
        true, separates communities the user is a leader of from those they're not a leader of."""

        community_list, leader_list, member_list = [], [], []

        for community in self.get_communities():

            if community.roles.is_member(user_pk):
                community_list.append(community)

                if split:

                    is_governor, through_role = community.roles.is_governor(user_pk)
                    is_owner, through_role = community.roles.is_owner(user_pk)

                    if is_governor or is_owner:
                        leader_list.append(community)
                    else:
                        member_list.append(community)

        if split:
            return leader_list, member_list
        else:
            return community_list

    def get_owner(self, *, owned_object: Model) -> Community:
        """Gets the owner of the owned object, which should always be a community."""
        # Note: this is still target-less since we don't need anything set as a target
        return owned_object.get_owner()

    def create_community(self, *, name: str) -> Community:
        """Creates a Community (or class descended from Community model) with actor as creator.
        Creates some additional structures by default but this can be overriden with bare=True."""
        roles = RoleHandler()
        roles.initialize_with_creator(creator=self.actor.pk)
        community = self.community_model.objects.create(name=name, roles=roles)
        self.set_default_permissions(community)
        return community

    # Read methods which require target to be set

    def get_members(self) -> list:
        """Gets all members of the community as list of user instances."""
        member_pks = self.target.roles.get_users_given_role("members")
        user_list = [User.objects.get(pk=pk) for pk in member_pks]
        return user_list

    def get_roles(self):
        """Get all roles set on the community."""
        return self.target.roles.get_roles()

    def get_custom_roles(self):
        """Gets all custom roles set on the community."""
        return self.target.roles.get_custom_roles()

    def get_role_names(self):
        """Get just the role names set on a community (no info on who has the roles)."""
        return self.target.roles.get_role_names()

    def get_users_given_role(self, *, role_name: str):
        """Given the role name, get the users who have that role."""
        return self.target.roles.get_users_given_role(role_name)

    def get_ownership_info(self, shorten_roles=False) -> dict:
        """Get the owners of the community."""
        owner_data = self.target.roles.get_owners()
        if shorten_roles:
            owner_data["roles"] = [role.split("_")[1] for role in owner_data["roles"]]
        return owner_data

    def get_governorship_info(self, shorten_roles=False) -> dict:
        """Get the governors of the community."""
        governor_data = self.target.roles.get_governors()
        if shorten_roles:
            governor_data["roles"] = [role.split("_")[1] for role in governor_data["roles"]]
        return governor_data

    def get_governance_info_as_text(self):
        """Gets governance info about the community as text."""
        return community_basic_info_to_text(self.target) + " " + community_governance_info_to_text(self.target)

    def get_condition_data(self, leadership_type) -> dict:
        """Gets condition data for conditions set on owners and governors."""
        return self.target.get_condition_data(leadership_type=leadership_type)

    def has_foundational_authority(self, *, actor) -> bool:
        """Returns True if actor has foundational authority, otherwise False."""
        return self.target.roles.is_owner(actor.pk)

    def has_governing_authority(self, *, actor) -> bool:
        """Returns True if actor has governing authority, otherwise False."""
        self.target.refresh_from_db()
        return self.target.roles.is_governor(actor.pk)

    def has_role_in_community(self, *, role: str, actor_pk: int) -> bool:
        """Returns True if actor has specific role in community. otherwise False."""
        return self.target.roles.has_specific_role(role, actor_pk)

    def get_users_with_ownership_privileges(self):
        ...

    def get_users_with_governorship_privileges(self):
        ...

    # Complex state updates

    def update_owners(self, *, new_owner_data):
        """Takes in a list of owners, adds those that are missing and removes those that
        are no longer there."""

        actions = []

        existing_owners = self.get_ownership_info()

        for new_owner in new_owner_data["individuals"]:
            if new_owner not in existing_owners["actors"]:
                action, result = self.add_owner_to_community(owner_pk=new_owner)
                actions.append(action)

        for old_owner in existing_owners["actors"]:
            if old_owner not in new_owner_data["individuals"]:
                action, result = self.remove_owner_from_community(owner_pk=old_owner)
                actions.append(action)

        for new_owner_role in new_owner_data["roles"]:
            if new_owner_role not in existing_owners["roles"]:
                action, result = self.add_owner_role_to_community(owner_role=new_owner_role)
                actions.append(action)

        for old_owner_role in existing_owners["roles"]:
            if old_owner_role not in new_owner_data["roles"]:
                action, result = self.remove_owner_role_from_community(owner_role=old_owner_role)
                actions.append(action)

        return actions

    def update_governors(self, *, new_governor_data):
        """Takes in a list of governors, adds those that are missing and removes
        those that are no longer there."""

        actions = []

        existing_governors = self.get_governorship_info()

        for new_governor in new_governor_data["individuals"]:
            if new_governor not in existing_governors["actors"]:
                action, result = self.add_governor_to_community(governor_pk=new_governor)
                actions.append(action)

        for old_governor in existing_governors["actors"]:
            if old_governor not in new_governor_data["individuals"]:
                action, result = self.remove_governor_from_community(governor_pk=old_governor)
                actions.append(action)

        for new_governor_role in new_governor_data["roles"]:
            if new_governor_role not in existing_governors["roles"]:
                action, result = self.add_governor_role_to_community(governor_role=new_governor_role)
                actions.append(action)

        for old_governor_role in existing_governors["roles"]:
            if old_governor_role not in new_governor_data["roles"]:
                action, result = self.remove_governor_role_from_community(governor_role=old_governor_role)
                actions.append(action)

        return actions

    def update_roles(self, *, role_data):
        """Takes in a list of roles and adds any which are missing from community."""

        actions = []

        existing_roles = self.get_roles()

        for index, role in role_data.items():
            # Check if role exists, if not make it
            if role["rolename"] not in existing_roles:
                action, result = self.add_role_to_community(role_name=role["rolename"])
                actions.append(action)

        return actions

    def update_role_membership(self, *, role_data):
        """Takes in a list of roles with members, adds any missing members and
        adds any which are missing from community."""

        actions = []

        for index, role in role_data.items():

            member_data = [int(pk) for pk in role["members"]]
            previous_members = self.get_users_given_role(role_name=role["rolename"])
            if not previous_members:
                previous_members = []  # returns nonetype if no role exists, which breaks set comparison
            people_to_add = list(set(member_data).difference(set(previous_members)))
            people_to_remove = list(set(previous_members).difference(set(member_data)))

            if people_to_add:
                action, result = self.add_people_to_role(role_name=role["rolename"], people_to_add=people_to_add)

                actions.append(action)

            if people_to_remove:
                action, result = self.remove_people_from_role(
                    role_name=role["rolename"], people_to_remove=people_to_remove)

                actions.append(action)

        return actions
