from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


# Create your models here.
class PermissionsResource(models.Model):

    # For now just using inbuilt generic relation, but may want to switch???
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    permitted_object = GenericForeignKey('content_type', 'object_id')
    ignore_defaults = models.BooleanField(default=False)

    # Basics

    def get_name(self):
        return "Permissions resource for " + self.permitted_object.get_name()

    def get_creator(self):
        target = self.permitted_object
        return target.get_creator()

    def get_unique_id(self):
        '''Unique id is always equal to: appname_modelname_pk'''
        return "permissionresources_permissionsresource_" + str(self.pk)

    # Read-only

    def get_items(self):
        result = []
        for item in self.permissionsitem_set.all():
            result.append(item.get_name())
        return result


class PermissionsItem(models.Model):

    actor = models.CharField(max_length=200)  # Replace with user model link
    action_type = models.CharField(max_length=200)  # Replace with choices field???
    resource = models.ForeignKey(PermissionsResource, on_delete=models.CASCADE)

    def get_name(self):
        return "Permission %s (%s for %s)" % (str(self.pk), self.action_type, self.actor)

    def get_unique_id(self):
        return "permissionresources_permissionsitem_" + str(self.pk)

    # Permissions-specific helpers

    def get_target(self):
        return self.resource.permitted_object

    def get_creator(self):
        target = self.get_target()
        return target.get_creator()

    def match_action_type(self, action_type):
        return self.action_type == action_type

    def match_actor(self, actor):
        return self.actor == actor