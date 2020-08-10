from typing import List, Tuple, Any

from django.db.models import QuerySet
from django.contrib.contenttypes.models import ContentType

from concord.actions.client import BaseClient
from concord.resources.models import Resource, Comment, CommentCatcher
from concord.resources import state_changes as sc


######################
### CommentClient ###
######################


class CommentClient(BaseClient):

    def swap_target_if_needed(self, create=False):
        if self.target.__class__.__name__ == "Action":
            catcher = CommentCatcher.objects.filter(action=self.target.pk)
            if catcher:
                self.target = catcher[0]
            else:
                if create:
                    # FIXME: is there a better way to get the community which owns the target of the action?
                    owner = self.target.target.get_owner()
                    owner_content_type = ContentType.objects.get_for_model(owner.__class__)
                    catcher = CommentCatcher.objects.create(
                        action=self.target.pk, owner_object_id=owner.pk, owner_content_type=owner_content_type
                    )
                    self.target = catcher

    def get_all_comments_on_target(self):
        self.swap_target_if_needed()
        content_type = ContentType.objects.get_for_model(self.target)
        return Comment.objects.filter(commented_object_id=self.target.id, commented_object_content_type=content_type)

    # state change method

    def add_comment(self, text):
        self.swap_target_if_needed(create=True)
        change = sc.AddCommentStateChange(text=text)
        return self.create_and_take_action(change)

    def edit_comment(self, pk, text):
        self.swap_target_if_needed(create=True)
        change = sc.EditCommentStateChange(pk=pk, text=text)
        return self.create_and_take_action(change)

    def delete_comment(self, pk):
        self.swap_target_if_needed(create=True)
        change = sc.DeleteCommentStateChange(pk=pk)
        return self.create_and_take_action(change)


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
        change = sc.AddItemStateChange(item_name=item_name)
        return self.create_and_take_action(change)

    def remove_item(self, *, item_pk: int) -> Tuple[int, Any]:
        change = sc.RemoveItemStateChange(item_pk=item_pk)
        return self.create_and_take_action(change)