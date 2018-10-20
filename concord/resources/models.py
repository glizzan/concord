from django.db import models


class Resource(models.Model):

    name = models.CharField(max_length=200)
    creator = models.CharField(max_length=200)  # Replace with link to account

    # Basics

    def get_name(self):
        return self.name

    def get_unique_id(self):
        '''Unique id is always equal to: appname_modelname_pk'''
        return "resources_resource_" + str(self.pk)

    def get_creator(self):
        return self.creator

    # Read-only

    def get_items(self):
        result = []
        for item in self.item_set.all():
            result.append(item.name)
        return result


class Item(models.Model):

    name = models.CharField(max_length=200)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    creator = models.CharField(max_length=200)  # Replace with account

    def get_name(self):
        return self.name

    def get_unique_id(self):
        '''Unique id is always equal to: appname_modelname_pk'''
        return "resources_item_" + str(self.pk)

    def get_creator(self):
        return self.creator

    # Basics