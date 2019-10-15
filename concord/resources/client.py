from typing import List, Tuple, Any

from django.db.models import QuerySet

from concord.actions.client import BaseClient

from concord.resources.models import Resource
from concord.resources import state_changes as sc


######################
### ResourceClient ###
######################

class ResourceClient(BaseClient):
    """
    The target of a resource client, if a target is required, is always a resource
    model. As with all Concord clients, a target must be set for all methods not 
    explicitly grouped as target-less methods.
    """

    # Target-less methods (don't require a target to be set ahead of time)

    def get_all_resources(self) -> QuerySet:
        return Resource.objects.all()

    # def get_all_resources_given_owner(self, *, owner_name: str) -> QuerySet:
    #     return Resource.objects.filter(owner=owner_name)

    def get_resource_given_name(self, *, resource_name: str) -> QuerySet:
        return Resource.objects.filter(name=resource_name)

    def get_resource_given_pk(self, *, pk: int) -> QuerySet:
        return Resource.objects.filter(pk=pk)

    def create_resource(self, *, name: str) -> Resource:
        created = Resource.objects.create(name=name, owner=self.actor.default_community)
        return created

    # Read only

    def get_items_on_resource(self) -> List[str]:
        return self.target.get_items()

    # State changes

    def change_name(self, *, new_name: str) -> Tuple[int, Any]:
        change = sc.ChangeResourceNameStateChange(new_name=new_name)
        return self.create_and_take_action(change)

    def add_item(self, *, item_name: str) -> Tuple[int, Any]:
        change = sc.AddItemResourceStateChange(item_name=item_name)
        return self.create_and_take_action(change)

    def remove_item(self, *, item_pk: int) -> Tuple[int, Any]:
        change = sc.RemoveItemResourceStateChange(item_pk=item_pk)
        return self.create_and_take_action(change)