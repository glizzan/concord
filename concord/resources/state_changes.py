"""Resource State Changes"""

import logging

from django.core.exceptions import ObjectDoesNotExist

from concord.actions.state_changes import BaseStateChange
from concord.resources.models import AbstractResource, AbstractItem, Resource, Item, Comment


logger = logging.getLogger(__name__)


#############################
### Comment State Changes ###
#############################


class AddCommentStateChange(BaseStateChange):
    """State Change to add a comment."""
    description = "Add comment"

    def __init__(self, text):
        self.text = text

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "add comment"

    def description_past_tense(self):
        return "added comment"

    def validate(self, actor, target):
        """Checks that text is a string of at least one character long."""
        if self.text and isinstance(self.text, str) and len(self.text) > 0:
            return True
        self.set_validation_error(message="Comment text must be a string at least one character long.")
        return False

    def implement(self, actor, target):

        comment = Comment(text=self.text, commentor=actor)
        comment.commented_object = target
        comment.owner = target.get_owner()

        comment.save()
        return comment


class EditCommentStateChange(BaseStateChange):
    """State Change to edit a comment."""
    description = "Edit comment"

    def __init__(self, pk, text):
        self.pk = pk
        self.text = text

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return f"edit comment {self.pk}"

    def description_past_tense(self):
        return f"edited comment {self.pk}"

    def validate(self, actor, target):
        """Checks that text is a string of at least one character long."""
        if self.text and isinstance(self.text, str) and len(self.text) > 0:
            return True
        self.set_validation_error(message="Comment text must be a string at least one character long.")
        return False

    def implement(self, actor, target):
        comment = Comment.objects.get(pk=self.pk)
        comment.text = self.text
        comment.save()
        return comment


class DeleteCommentStateChange(BaseStateChange):
    """State Change to delete a comment."""
    description = "Delete comment"

    def __init__(self, pk):
        self.pk = pk

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return f"delete comment {self.pk}"

    def description_past_tense(self):
        return f"deleted comment {self.pk}"

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        comment = Comment.objects.get(pk=self.pk)
        comment.delete()
        return self.pk


#####################################
### Resource & Item State Changes ###
#####################################

class ChangeResourceNameStateChange(BaseStateChange):
    """State Change to change a resource name."""
    description = "Change name of resource"
    preposition = "for"

    def __init__(self, new_name):
        self.new_name = new_name

    @classmethod
    def get_settable_classes(cls):
        return [AbstractResource, AbstractItem, Resource, Item]

    def description_present_tense(self):
        return f"change name of resource to {self.new_name}"

    def description_past_tense(self):
        return f"changed name of resource to {self.new_name}"

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        target.name = self.new_name
        target.save()
        return target


class AddItemStateChange(BaseStateChange):
    """State Change to add item to a resource."""
    description = "Add item to resource"

    def __init__(self, item_name):
        self.item_name = item_name

    @classmethod
    def get_settable_classes(cls):
        """An AddItem permission can be set on an item, a resource, or on the community that owns the
        item or resource."""
        return [Resource, Item] + cls.get_community_models()

    def description_present_tense(self):
        return f"add item {self.item_name}"

    def description_past_tense(self):
        return f"added item {self.item_name}"

    def validate(self, actor, target):
        """
        put real logic here
        """
        if actor and target and self.item_name:
            return True
        return False

    def implement(self, actor, target):
        item = Item.objects.create(name=self.item_name, resource=target, owner=actor.default_community)
        return item


class RemoveItemStateChange(BaseStateChange):
    """State Change to remove item from a resource."""
    description = "Remove item from resource"
    preposition = "from"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    @classmethod
    def get_settable_classes(cls):
        return [AbstractResource, AbstractItem, Resource, Item]

    def description_present_tense(self):
        return f"remove item with pk {self.item_pk}"

    def description_past_tense(self):
        return f"removed item with pk {self.item_pk}"

    def validate(self, actor, target):
        """
        put real logic here
        """
        if actor and target and self.item_pk:
            return True
        return False

    def implement(self, actor, target):
        try:
            item = Item.objects.get(pk=self.item_pk)
            item.delete()
            return True
        except ObjectDoesNotExist as exception:
            logger.warning(exception)
            return False
