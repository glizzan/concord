from actions.clients import BaseActionClient

from resources.models import Resource
from resources import state_changes as sc


######################
### ResourceClient ###
######################

class ResourceClient(BaseActionClient):
    pass

    # Read only

    # Create only

    def create_resource(self, name):
        return Resource.objects.create(name=name, creator=self.actor)

    # State changes

    def add_item(self, item_name, target=None):
        change = sc.AddItemResourceStateChange(item_name=item_name)
        return self.create_and_take_action(change, target)

    def remove_item(self, item_pk, target=None):
        change = sc.RemoveItemResourceStateChange(item_pk=item_pk)
        return self.create_and_take_action(change, target)