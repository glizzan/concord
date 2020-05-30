from concord.conditionals.client import ConditionalClient
from concord.communities.client import CommunityClient
from concord.permission_resources.client import PermissionResourceClient
from concord.resources.client import ResourceClient


class ClientInterface(object):

    # TODO: possibly make a helper method to make it easier to override individual clients, instead of having to do
    # something like:   ClientInterface(actor=me)   ClientInterface.communities = GroupClient(actor=me) ?
    # like an option to pass in communities_class?

    communities = CommunityClient()
    conditions = ConditionalClient()
    permissions = PermissionResourceClient()
    resources = ResourceClient() 

    def __init__(self, default_actor=None):

        if default_actor:
            self.communities.set_actor(actor=default_actor)
            self.conditions.set_actor(actor=default_actor)
            self.permissions.set_actor(actor=default_actor)
            self.resources.set_actor(actor=default_actor)

    def get_clients_to_change(self, client_type=None, all_clients=True):
        # NOTE: check we're not accidentally dereferencing here?
        clients = []
        
        if all_clients:
            for client_type_in_list in ["communities", "conditions", "permissions", "resources"]:
                clients.append(getattr(self, client_type_in_list))
        else:
            if client_type:
                clients.append(getattr(self, client_type))
            else:
                raise AttributeError("Must supply either client_type or set all_clients to true when setting target")

        return clients

    def set_target(self, target, client_type=None, all_clients=True):

        for client in self.get_clients_to_change(client_type, all_clients):
            client.set_target(target=target)

    def set_actor(self, actor, clients):

        for client in self.get_clients_to_change(client_type, all_clients):
            client.set_actor(actor=actor)

