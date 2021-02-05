"""Client for Resources."""

from typing import List, Tuple, Any

from django.db.models import QuerySet
from django.contrib.contenttypes.models import ContentType

from concord.actions.client import BaseClient
from concord.resources.models import Resource, Comment, CommentCatcher, SimpleList
from concord.resources import state_changes as sc


######################
### CommentClient ###
######################


class CommentClient(BaseClient):
    """Client for interacting with Comment model."""
    app_name = "resources"

    def swap_target_if_needed(self, create=False):
        """The target of CommentClient needs to be the CommentCatcher object, but sometimes the target is
        set to action instead.  We automatically handle that instead of making the user do it."""
        if self.target.__class__.__name__ == "Action":
            catcher = CommentCatcher.objects.filter(action=self.target.pk)
            if catcher:
                self.target = catcher[0]
            else:
                if create:
                    owner = self.target.target.get_owner()
                    owner_content_type = ContentType.objects.get_for_model(owner.__class__)
                    catcher = CommentCatcher.objects.create(
                        action=self.target.pk, owner_object_id=owner.pk, owner_content_type=owner_content_type
                    )
                    self.target = catcher

    def get_comment(self, pk):
        """Gets specific comment given pk."""
        return Comment.objects.get(pk=pk)

    def get_all_comments_on_target(self):
        """Gets all comment son the current target."""
        self.swap_target_if_needed()
        content_type = ContentType.objects.get_for_model(self.target)
        return Comment.objects.filter(commented_object_id=self.target.id, commented_object_content_type=content_type)

    # state change method

    def add_comment(self, text):
        """Add a comment to the target."""
        self.swap_target_if_needed(create=True)
        change = sc.AddCommentStateChange(text=text)
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
    app_name = "resources"

    # Target-less methods (don't require a target to be set ahead of time)

    def get_all_resources(self) -> QuerySet:
        """Get all resources in the system."""
        return Resource.objects.all()

    def get_resource_given_name(self, *, resource_name: str) -> QuerySet:
        """Get a resource given a unique name."""
        return Resource.objects.filter(name=resource_name)

    def get_resource_given_pk(self, *, pk: int) -> QuerySet:
        """Get a resource given pk."""
        return Resource.objects.filter(pk=pk)

    def create_resource(self, *, name: str) -> Resource:
        """Create a resource given name of resource to be created."""
        resource = Resource.objects.create(name=name, owner=self.actor.default_community)
        self.set_default_permissions(resource)
        return resource

    # Read only

    def get_items_on_resource(self) -> List[str]:
        """Get items on targtet resource."""
        return self.target.get_items()


##################
### ListClient ###
##################


class ListClient(BaseClient):
    """Client for interacting with Lists."""
    app_name = "resources"

    # Read methods

    def get_list(self, pk):
        return SimpleList.objects.get(pk=pk)

    def get_all_lists(self):
        return SimpleList.objects.all()

    def get_all_lists_given_owner(self, owner):
        content_type = ContentType.objects.get_for_model(owner)
        return SimpleList.objects.filter(
            owner_content_type=content_type, owner_object_id=owner.id)
