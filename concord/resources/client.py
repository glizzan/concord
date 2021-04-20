"""Client for Resources."""

from django.contrib.contenttypes.models import ContentType

from concord.actions.client import BaseClient
from concord.resources.models import Comment, CommentCatcher, SimpleList, Document
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


######################
### DocumentClient ###
######################


class DocumentClient(BaseClient):
    """Client for interacting with Documents."""
    app_name = "resources"

    # Read methods

    def get_document(self, pk):
        return Document.objects.get(pk=pk)

    def get_all_documents(self):
        return Document.objects.all()

    def get_all_documents_given_owner(self, owner):
        content_type = ContentType.objects.get_for_model(owner)
        return Document.objects.filter(
            owner_content_type=content_type, owner_object_id=owner.id)
