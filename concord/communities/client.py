import json
from typing import Tuple, Any

from django.db.models import Model
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

from concord.actions.client import BaseClient
from concord.actions.models import PermissionedModel

from concord.communities.models import Community
from concord.communities.customfields import RoleHandler
from concord.communities import state_changes as sc


######################
### CommunityClient ###
######################

class CommunityClient(BaseClient):
    """
    The target of a community client, if a target is required, is always a community 
    model. As with all Concord clients, a target must be set for all methods not 
    explicitly grouped as target-less methods.
    """

    # Target-less methods (don't require a target to be set ahead of time)

    def set_target_community(self, *, community_name: str = None, community_pk: str = None):
        '''
        Sets target community given a name or pk. If the user already has the community object, 
        it can be set directly using the parent method set_target.
        '''
        self.target = self.get_community(community_name=community_name, community_pk=community_pk)

    def get_community(self, *, community_name: str = None, community_pk: str = None) -> Community:
        '''
        Takes either community name or PK and returns Community object.  If both are supplied,
        returns Community object corresponding to community_pk.
        '''
        if community_pk:
            return Community.objects.get(pk=community_pk)
        if community_name:
            return Community.objects.get(name=community_name)
        raise Exception("Get community require community name or community pk")

    def get_communities(self):
        ... 

    def get_owner(self, *, owned_object: Model) -> Community:
        """Gets the owner of the owned object, which should always be a community."""
        # Note: this is still target-less since we don't need anything set as a target
        return owned_object.get_owner()

    def create_community(self, *, name: str) -> Community:
        roles = RoleHandler()
        roles.initialize_with_creator(creator=self.actor.pk)
        community = Community.objects.create(name=name, roles=roles)
        return community

    # Read methods which require target to be set

    def get_target(self) -> Community:
        return self.target

    def get_members(self) -> list:
        member_pks = self.target.roles.get_users_given_role("members")
        user_list = [User.objects.get(pk=pk) for pk in member_pks]
        return user_list

    def get_roles(self):
        return self.target.roles.get_roles()

    def get_custom_roles(self):
        return self.target.roles.get_custom_roles()

    def get_role_names(self):
        return self.target.roles.get_role_names()

    def get_users_given_role(self, *, role_name: str):
        return self.target.roles.get_users_given_role(role_name)

    def get_ownership_info(self, shorten_roles=False) -> dict:
        owner_data = self.target.roles.get_owners()
        if shorten_roles:
            owner_data["roles"] = [role.split("_")[1] for role in owner_data["roles"]]
        return owner_data

    def get_governorship_info(self, shorten_roles=False) -> dict:
        governor_data = self.target.roles.get_governors()
        if shorten_roles:
            governor_data["roles"] = [role.split("_")[1] for role in governor_data["roles"]]
        return governor_data

    def has_foundational_authority(self, *, actor) -> bool:  # Also returns role
        return self.target.roles.is_owner(actor.pk) 

    def has_governing_authority(self, *, actor) -> bool:  # Also returns role
        self.target.refresh_from_db()  # FIXME: seems expensive to do this every time?
        return self.target.roles.is_governor(actor.pk) # FIXME: actor should be pk

    def has_role_in_community(self, *, role: str, actor_pk: int) -> bool:
        return self.target.roles.has_specific_role(role, actor_pk)

    # State changes

    def make_self_owned(self):
        pass

    def add_members(self, member_pk_list: list) -> Tuple[int, Any]:
        change = sc.AddMembersStateChange(member_pk_list=member_pk_list)
        return self.create_and_take_action(change)

    def remove_members(self, member_pk_list: list) -> Tuple[int, Any]:
        change = sc.RemoveMembersStateChange(member_pk_list=member_pk_list)
        return self.create_and_take_action(change)

    def add_governor(self, *, governor_pk: int) -> Tuple[int, Any]:
        change = sc.AddGovernorStateChange(governor_pk=governor_pk)
        return self.create_and_take_action(change)

    def remove_governor(self, *, governor_pk: int) -> Tuple[int, Any]:
        change = sc.RemoveGovernorStateChange(governor_pk=governor_pk)
        return self.create_and_take_action(change)

    def add_governor_role(self, *, governor_role: str) -> Tuple[int, Any]:
        change = sc.AddGovernorRoleStateChange(role_name=governor_role)
        return self.create_and_take_action(change)

    def remove_governor_role(self, *, governor_role: str) -> Tuple[int, Any]:
        change = sc.RemoveGovernorRoleStateChange(role_name=governor_role)
        return self.create_and_take_action(change)

    def add_owner(self, *, owner_pk: int) -> Tuple[int, Any]:
        change = sc.AddOwnerStateChange(owner_pk=owner_pk)
        return self.create_and_take_action(change)

    def remove_owner(self, *, owner_pk: int) -> Tuple[int, Any]:
        change = sc.RemoveOwnerStateChange(owner_pk=owner_pk)
        return self.create_and_take_action(change)

    def add_owner_role(self, *, owner_role: str) -> Tuple[int, Any]:
        change = sc.AddOwnerRoleStateChange(role_name=owner_role)
        return self.create_and_take_action(change)

    def remove_owner_role(self, *, owner_role: str) -> Tuple[int, Any]:
        change = sc.RemoveOwnerRoleStateChange(role_name=owner_role)
        return self.create_and_take_action(change)

    def change_name(self, *, new_name: str) -> Tuple[int, Any]:
        change = sc.ChangeNameStateChange(new_name=new_name)
        return self.create_and_take_action(change)

    def add_role(self, *, role_name: str) -> Tuple[int, Any]:
        change = sc.AddRoleStateChange(role_name=role_name)
        return self.create_and_take_action(change)

    def remove_role(self, *, role_name: str) -> Tuple[int, Any]:
        change = sc.RemoveRoleStateChange(role_name=role_name)
        return self.create_and_take_action(change)

    def add_people_to_role(self, *, role_name: str, people_to_add: list) -> Tuple[int, Any]:
        change = sc.AddPeopleToRoleStateChange(role_name=role_name, people_to_add=people_to_add)
        return self.create_and_take_action(change)

    def remove_people_from_role(self, *, role_name: str, people_to_remove: list) -> Tuple[int, Any]:
        change = sc.RemovePeopleFromRoleStateChange(role_name=role_name, people_to_remove=people_to_remove)
        return self.create_and_take_action(change)

    # Complex/multiple state changes

    def update_owners(self, *, new_owner_data):
        """Takes in a list of owners, adds those that are missing and removes those that
        are no longer there."""

        actions = []

        existing_owners = self.get_ownership_info()

        for new_owner in new_owner_data["individuals"]:
            if new_owner not in existing_owners["actors"]:
                action, result = self.add_owner(owner_name=new_owner)
                actions.append(action)

        for old_owner in existing_owners["actors"]:
            if old_owner not in new_owner_data["individuals"]:
                action, result = self.remove_owner(owner_name=old_owner)
                actions.append(action)

        for new_owner_role in new_owner_data["roles"]:
            if new_owner_role not in existing_owners["roles"]:
                action, result = self.add_owner_role(owner_role=new_owner_role)
                actions.append(action)

        for old_owner_role in existing_owners["roles"]:
            if old_owner_role not in new_owner_data["roles"]:
                community_pk, old_role = old_owner_role.split("_") # Make better API to get roles, and remove this?
                action, result = self.remove_owner_role(owner_role=old_role)
                actions.append(action)

        return actions

    def update_governors(self, *, new_governor_data):
        """Takes in a list of governors, adds those that are missing and removes 
        those that are no longer there."""

        actions = []

        existing_governors = self.get_governorship_info()

        for new_governor in new_governor_data["individuals"]:
            if new_governor not in existing_governors["actors"]:
                action, result = self.add_governor(governor_name=new_governor)
                actions.append(action)

        for old_governor in existing_governors["actors"]:
            if old_governor not in new_governor_data["individuals"]:
                action, result = self.remove_governor(governor_name=old_governor)
                actions.append(action)

        for new_governor_role in new_governor_data["roles"]:
            if new_governor_role not in existing_governors["roles"]:
                action, result = self.add_governor_role(governor_role=new_governor_role)
                actions.append(action)

        for old_governor_role in existing_governors["roles"]:
            if old_governor_role not in new_governor_data["roles"]:
                community_pk, old_role = old_governor_role.split("_") # Make better API to get roles, and remove this?
                action, result = self.remove_governor_role(governor_role=old_role)
                actions.append(action)

        return actions


    def update_roles(self, *, role_data):
        """Takes in a list of roles and adds any which are missing from community."""

        actions = []

        existing_roles = self.get_roles()

        for index, role in role_data.items():
            # Check if role exists, if not make it
            if role["rolename"] not in existing_roles:
                action, result = self.add_role(role_name=role["rolename"])
                actions.append(action)

        return actions

    def update_role_membership(self, *, role_data):
        """Takes in a list of roles with members, adds any missing members and 
        adds any which are missing from community."""
        
        # NOTE: this requires two different permissions

        actions = []

        for index, role in role_data.items():

            member_data = [int(pk) for pk in role["members"]]
            previous_members = self.get_users_given_role(role_name=role["rolename"])
            if not previous_members:  
                previous_members = []  # returns nonetype if no role exists, which breaks set comparison
            people_to_add = list(set(member_data).difference(set(previous_members)))
            people_to_remove = list(set(previous_members).difference(set(member_data)))
            
            if people_to_add:
                action, result = self.add_people_to_role(role_name=role["rolename"], 
                    people_to_add=people_to_add)
                actions.append(action)

            if people_to_remove:
                action, result = self.remove_people_from_role(role_name=role["rolename"], 
                    people_to_remove=people_to_remove)
                actions.append(action)

        return actions

