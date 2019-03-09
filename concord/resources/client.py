from actions.clients import BaseActionClient

from concord.resources.models import Resource
from concord.resources import state_changes as sc


######################
### ResourceClient ###
######################

class ResourceClient(BaseActionClient):
    pass

    # Read only

    def get_all_resources(self):
        return Resource.objects.all()

    def get_all_resources_given_owner(self, owner_name):
        return Resource.objects.filter(owner=owner_name)

    def get_items_on_resource(self):
        return self.target.get_items()

    def get_resource_given_name(self, resource_name):
        return Resource.objects.filter(name=resource_name)

    def get_resource_given_pk(self, pk):
        return Resource.objects.filter(pk=pk)

    # Create only

    def create_resource(self, name):
        created = Resource.objects.create(name=name, owner=self.actor)
        return created

    # State changes

    def change_name(self, new_name, target=None):
        change = sc.ChangeResourceNameStateChange(new_name=new_name)
        return self.create_and_take_action(change, target)

    def add_item(self, item_name, target=None):
        change = sc.AddItemResourceStateChange(item_name=item_name)
        return self.create_and_take_action(change, target)

    def remove_item(self, item_pk, target=None):
        change = sc.RemoveItemResourceStateChange(item_pk=item_pk)
        return self.create_and_take_action(change, target)