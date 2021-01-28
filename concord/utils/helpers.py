import inspect

from concord.utils.lookups import get_all_state_changes, get_all_clients


class Attributes(object):
    """Hack to allow nested attributes on Changes."""
    ...


class Changes(object):
    """Helper object which lets developers easily access change types."""

    def __init__(self):

        for change in get_all_state_changes():

            tokens = change.get_change_type().split(".")
            app_name = (tokens[1] if "concord" in tokens else tokens[0]).capitalize()
            change_name = (tokens[3] if "concord" in tokens else tokens[2]).replace("StateChange", "")

            app_name = "Permissions" if app_name == "Permission_resources" else app_name

            if not hasattr(self, app_name):
                setattr(self, app_name, Attributes())

            app_attr = getattr(self, app_name)
            setattr(app_attr, change_name, change.get_change_type())


class Client(object):
    """Helper object which lets developers easily access all clients at once.

    If supplied with actor and/or target, will instantiate clients with that actor and target.

    limit_to is a list of client names, if supplied actors and targets will only be supplied to
    the specified clients.
    """

    community_client_override = None

    def __init__(self, actor=None, target=None, limit_to=None):

        self.client_names = []

        for client_class in get_all_clients():

            client_attribute_name = client_class.__name__.replace("Client", "")

            if not limit_to or client_attribute_name in limit_to:
                client_instance = client_class(actor=actor, target=target)
            else:
                client_instance = client_class()

            if client_attribute_name == "Community":       # Helps deal with multiple community groups
                client_attribute_name = "Concord" + client_attribute_name

            setattr(self, client_attribute_name, client_instance)
            self.client_names.append(client_attribute_name)

    def get_clients(self):
        """Gets a list of client objects set as attributes on Client()."""
        return [getattr(self, client_name) for client_name in self.client_names]

    def update_actor_on_all(self, actor):
        """Update actor for all clients."""
        for client in self.get_clients():
            client.set_actor(actor=actor)

    def update_target_on_all(self, target):
        """Update target for all clients."""
        for client in self.get_clients():
            client.set_target(target=target)

    def set_mode_for_all(self, mode):
        for client in self.get_clients():
            client.mode = mode

    @property
    def Community(self):
        """Projects that use Concord may create a new model and client, descending from the Community model and
        CommunityClient. To handle this scenario, we look for Clients with an attribute community_model and, if
        something other than the CommunityClient exists, we use that. Users can override this behavior by
        explicitly setting community_client_override to whatever client they want to use."""

        if self.community_client_override:
            return self.community_client_override

        community_clients = [client for client in self.get_clients() if hasattr(client, "community_model")]

        if len(community_clients) == 1:
            return community_clients[0]

        for client in community_clients:
            if client.__class__.__name__ != "CommunityClient":
                return client