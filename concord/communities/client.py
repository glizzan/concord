import json
from typing import Tuple, Any

from django.db.models import Model

from concord.actions.client import BaseClient
from concord.actions.models import PermissionedModel

from concord.communities.models import Community, AuthorityHandler, RoleSet
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
        # Note: this is still target-less since we don't need anything set as a target
        community_name = owned_object.get_owner()
        return self.get_community(community_name=community_name)

    def create_community(self, *, name: str) -> Community:
        # TODO: should we have to specify owner_type here?
        return Community.objects.create(name=name, owner_type="com", creator=self.actor)

    # Read methods which require target to be set

    def get_target(self) -> Community:
        return self.target

    def get_members(self) -> list:
        return self.target.roleset.list_users_given_role("members")

    def get_assigned_roles(self):
        return self.target.roleset.get_assigned_roles()

    def get_assigned_role_names(self):
        return list(self.target.roleset.get_assigned_roles().keys())

    def get_users_given_role(self, *, role_name: str):
        return self.target.roleset.list_users_given_role(role_name)

    def get_ownership_info(self) -> dict:
        return self.target.authorityhandler.get_owners()

    def get_governorship_info(self) -> dict:
        return self.target.authorityhandler.get_governors()

    def has_foundational_authority(self, *, actor: str) -> bool:
        authHandler = AuthorityHandler.objects.get(community=self.target)
        return authHandler.is_owner(actor)

    def has_governing_authority(self, *, actor: str) -> bool:
        authHandler = AuthorityHandler.objects.get(community=self.target)
        return authHandler.is_governor(actor)

    def has_role_in_community(self, *, role: str, actor: str) -> bool:
        return self.target.roleset.user_has_assigned_role(role, actor)

    # State changes

    def add_governor(self, *, governor_name: str) -> Tuple[int, Any]:
        change = sc.AddGovernorStateChange(governor_name=governor_name)
        return self.create_and_take_action(change)

    def add_governor_role(self, *, governor_role: str) -> Tuple[int, Any]:
        change = sc.AddGovernorRoleStateChange(role_name=governor_role)
        return self.create_and_take_action(change)

    def add_owner(self, *, owner_name: str) -> Tuple[int, Any]:
        change = sc.AddOwnerStateChange(owner_name=owner_name)
        return self.create_and_take_action(change)

    def add_owner_role(self, *, owner_role: str) -> Tuple[int, Any]:
        change = sc.AddOwnerRoleStateChange(role_name=owner_role)
        return self.create_and_take_action(change)

    # TODO: add remove versions of governor, owner, gov role, owner role SCs

    def change_name(self, *, new_name: str) -> Tuple[int, Any]:
        change = sc.ChangeNameStateChange(new_name=new_name)
        return self.create_and_take_action(change)

    def add_assigned_role(self, *, role_name: str) -> Tuple[int, Any]:
        change = sc.AddRoleStateChange(role_name=role_name)
        return self.create_and_take_action(change)

    def remove_assigned_role(self, *, role_name: str) -> Tuple[int, Any]:
        change = sc.RemoveRoleStateChange(role_name=role_name)
        return self.create_and_take_action(change)

    def add_people_to_role(self, *, role_name: str, people_to_add: list) -> Tuple[int, Any]:
        change = sc.AddPeopleToRoleStateChange(role_name=role_name, people_to_add=people_to_add)
        return self.create_and_take_action(change)

    def remove_people_from_role(self, *, role_name: str, people_to_remove: list) -> Tuple[int, Any]:
        change = sc.RemovePeopleFromRoleStateChange(role_name=role_name, people_to_remove=people_to_remove)
        return self.create_and_take_action(change)

    def add_member(self, *, name: str) -> Tuple[int, Any]:
        change = sc.AddPeopleToRoleStateChange(role_name="members", people_to_add=[name])
        return self.create_and_take_action(change)

    def remove_member(self, *, name: str) -> Tuple[int, Any]:
        change = sc.RemovePeopleFromRoleStateChange(role_name="members", people_to_remove=[name])
        return self.create_and_take_action(change)

    # Complex/multiple state changes

    def update_roles(self, *, role_data):
        """Takes in a list of roles and adds any which are missing from community."""

        actions, results = [], []

        existing_roles = self.get_assigned_roles()

        for index, role in role_data.items():
            # Check if role exists, if not make it
            if role["rolename"] not in existing_roles:
                action, result = self.add_assigned_role(role_name=role["rolename"])
                actions.append(action)
                results.append(result)

        return actions, results 

    def update_role_membership(self, *, role_data):
        """Takes in a list of roles with members, adds any missing members and 
        adds any which are missing from community."""
        
        # NOTE: this requires two different permissions

        actions, results = [], []

        for index, role in role_data.items():

            member_data = role["members"].split(", ")
            previous_members = self.get_users_given_role(role_name=role["rolename"])
            if not previous_members:  
                previous_members = []  # returns nonetype if no role exists, which breaks set comparison
            people_to_add = list(set(member_data).difference(set(previous_members)))
            people_to_remove = list(set(previous_members).difference(set(member_data)))
            
            if people_to_add:
                action, result = self.add_people_to_role(role_name=role["rolename"], 
                    people_to_add=people_to_add)
                actions.append(action)
                results.append(result)

            if people_to_remove:
                action, result = self.remove_people_from_role(role_name=role["rolename"], 
                    people_to_remove=people_to_remove)
                actions.append(action)
                results.append(result)

        return actions, results

