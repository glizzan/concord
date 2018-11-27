from django.db import models

from actions.models import PermissionedModel


class Resource(PermissionedModel):

    name = models.CharField(max_length=200)

    # Basics

    def get_name(self):
        return self.name

    # Read-only

    def get_items(self):
        result = []
        for item in self.item_set.all():
            result.append(item.name)
        return result
        

class Item(PermissionedModel):

    name = models.CharField(max_length=200)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)

    def get_name(self):
        return self.name
