"""Resource models."""

from typing import List

from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.auth.models import User

from concord.actions.models import PermissionedModel


class Comment(PermissionedModel):
    """Comment model."""

    commented_object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    commented_object_id = models.PositiveIntegerField()
    commented_object = GenericForeignKey('commented_object_content_type', 'commented_object_id')

    commentor = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    text = models.CharField(max_length=1000)


class CommentCatcher(PermissionedModel):
    """The comment catcher model is a hack to deal with leaving comments on non-permissioned models.  Right now,
    the only model we're doing this for is Action."""

    action = models.IntegerField(unique=True)

    def get_name(self):
        """Get name of object."""
        return f"Comment catcher for action {self.action}"


class AbstractResource(PermissionedModel):
    """Abstract Resource model contains basic functionality that developers can inherit."""

    name = models.CharField(max_length=200)

    class Meta:
        abstract = True

    # Basics

    def get_name(self):
        """Gets name of abstract resource."""
        return self.name

    # Read-only

    def get_items(self) -> List[str]:
        """Gets item associated with resource."""
        result = []
        for item in self.item_set.all():
            result.append(item.name)
        return result


class AbstractItem(PermissionedModel):
    """Abstract item model that developers can inherit from."""

    name = models.CharField(max_length=200)

    class Meta:
        abstract = True

    def get_name(self):
        """Get name of abstract item."""
        return self.name


class Resource(AbstractResource):
    """Non-abstract resource model."""

    def get_nested_objects(self):
        """Get objects that Resource is nested on, in this case the owner."""
        return [self.get_owner()]


class Item(AbstractItem):
    """Non-abstract item model."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
