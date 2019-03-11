import json

from concord.actions.clients import BaseActionClient

from concord.communities.models import Community, AuthorityHandler, RoleSet
from concord.communities import state_changes as sc


######################
### CommunityClient ###
######################

class CommunityClient(BaseActionClient):
    pass

    # Read only

    def get_owner(self, target):
        community_name = target.get_owner()
        return Community.objects.get(name=community_name) 

    def get_members(self, community_name):
        community = Community.objects.get(name=community_name)
        return community.roleset.list_users_given_role("members")

    def get_ownership_info(self, community_name):
        community = Community.objects.get(name=community_name)
        return community.authorityhandler.get_owners()

    def get_governorship_info(self, community_name):
        community = Community.objects.get(name=community_name)
        return community.authorityhandler.get_governors()

    def get_all_communities(self):
        pass

    def get_community_given_name(self, community_name):
        pass

    def get_community_given_pk(self, pk):
        return Community.objects.get(pk=pk)

    def has_foundational_authority(self, community, actor):
        authHandler = AuthorityHandler.objects.get(community=community)
        return authHandler.is_owner(actor)

    def has_governing_authority(self, community, actor):
        authHandler = AuthorityHandler.objects.get(community=community)
        return authHandler.is_governor(actor)

    def has_role_in_community(self, community_pk, role, actor):
        community = Community.objects.get(pk=community_pk)
        return community.roleset.user_has_assigned_role(role, actor)


    # Role-related reads

    def get_assigned_roles(self, community_pk):
        community = Community.objects.get(pk=community_pk)
        return community.roleset.get_assigned_roles()


    # Create only

    def create_community(self, name):
        # TODO: should we have to specify owner_type here?
        created = Community.objects.create(name=name, owner_type="com")
        # TODO: should authority handler be created via signal?
        governors = json.dumps({ "actors": [self.actor], "roles": []})
        owners = json.dumps({ "actors": [self.actor], "roles": []})
        handler = AuthorityHandler.objects.create(community=created, governors=governors, owners=owners)
        roleset = RoleSet.objects.create(community=created, 
            assigned=json.dumps({ "members": [self.actor] }))
        return created

    # State changes

    def add_governor(self, governor_name, target=None):
        change = sc.AddGovernorStateChange(governor_name=governor_name)
        return self.create_and_take_action(change, target)

    def add_governor_role(self, governor_role, target=None):
        change = sc.AddGovernorRoleStateChange(role_name=governor_role)
        return self.create_and_take_action(change, target)

    def add_owner(self, owner_name, target=None):
        change = sc.AddOwnerStateChange(owner_name=owner_name)
        return self.create_and_take_action(change, target)

    def add_owner_role(self, owner_role, target=None):
        change = sc.AddOwnerRoleStateChange(role_name=owner_role)
        return self.create_and_take_action(change, target)

    # TODO: add remove versions of governor, owner, gov role, owner role SCs

    def change_name(self, new_name, target=None):
        change = sc.ChangeNameStateChange(new_name=new_name)
        return self.create_and_take_action(change, target)

    def add_assigned_role(self, role_name, target=None):
        change = sc.AddRoleStateChange(role_name=role_name)
        return self.create_and_take_action(change, target)

    def remove_assigned_role(self, role_name, target=None):
        change = sc.RemoveRoleStateChange(role_name=role_name)
        return self.create_and_take_action(change, target)

    def add_people_to_role(self, role_name, people_to_add, target=None):
        change = sc.AddPeopleToRoleStateChange(role_name=role_name, people_to_add=people_to_add)
        return self.create_and_take_action(change, target)

    def remove_people_from_role(self, role_name, people_to_remove, target=None):
        change = sc.RemovePeopleFromRoleStateChange(role_name=role_name, people_to_remove=people_to_remove)
        return self.create_and_take_action(change, target)

    def add_member(self, person_to_add, target=None):
        change = sc.AddPeopleToRoleStateChange(role_name="members", people_to_add=[person_to_add])
        return self.create_and_take_action(change, target)

    def remove_member(self, person_to_remove, target=None):
        change = sc.RemovePeopleFromRoleStateChange(role_name="members", 
            people_to_remove=[person_to_remove])
        return self.create_and_take_action(change, target)
