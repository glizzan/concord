from typing import List

from django.db import models

from concord.actions.models import PermissionedModel


class AbstractResource(PermissionedModel):

    name = models.CharField(max_length=200)

    class Meta:
        abstract = True

    # Basics

    def get_name(self):
        return self.name

    # Read-only

    def get_items(self) -> List[str]:
        result = []
        for item in self.item_set.all():
            result.append(item.name)
        return result


class AbstractItem(PermissionedModel):

    name = models.CharField(max_length=200)

    class Meta:
        abstract = True

    def get_name(self):
        return self.name


class Resource(AbstractResource):
    ...
    

class Item(AbstractItem):

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)


