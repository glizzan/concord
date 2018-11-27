from actions.clients import BaseActionClient

from communities.models import Community, AuthorityHandler
from communities import state_changes as sc


######################
### CommunityClient ###
######################

class CommunityClient(BaseActionClient):
    pass

    # Read only

    def get_all_communities(self):
        pass

    def get_community_given_name(self, community_name):
        pass

    def get_community_given_pk(self, pk):
        return Community.objects.get(pk=pk)

    def does_actor_have_default_permission_on_community(self, action):
        # FIXME: This is super hacky because we're saving the owner as, variously, the object 
        # itself, and its pk.  
        community_name = action.target.get_owner()
        community = Community.objects.get(name=community_name)  
        # Check action's actor against that community
        return community.authorityhandler.has_default_permission(action)

    # Create only

    def create_community(self, name):
        # TODO: should we have to specify owner_type here?
        created = Community.objects.create(name=name, owner_type="com")
        # TODO: should authority handler be created via signal?
        handler = AuthorityHandler.objects.create(community=created, governors=self.actor)
        return created

    # State changes

    def change_name(self, new_name, target=None):
        change = sc.ChangeNameStateChange(new_name=new_name)
        return self.create_and_take_action(change, target)